"""
CareerCompass — RAG Taxonomy Matching

Stage 3 of the syllabus pipeline. The extractor leaves each skill as the
phrase the syllabus used and `canonical` set to None; this module resolves
that phrase onto a shared identifier, so a course that teaches "GazeboSim
Harmonic" and a job posting that wants "Gazebo simulator" can be compared
at all.

    extracted term + evidence
            ↓
    exact alias lookup                      free, and right when it hits
            ↓ miss
    vector retrieval over the taxonomy      recall: ten plausible entries
            ↓
    reranking with the full record          precision: which one is it
            ↓ still ambiguous
    constrained LLM selection               chooses an id or no_match
            ↓
    confidence check → accept or review

Every stage narrows the candidate set and none of them can invent an
identifier: the LLM only ever picks from what retrieval supplied. A term
that survives to the end without a confident answer is queued for a human
rather than guessed at, because a wrong canonical id is invisible once it
is stored, and it quietly corrupts every gap analysis built on top of it.

Usage:
    from careercompass.skills.matcher import SkillMatcher

    matcher = SkillMatcher.build()
    matches = matcher.match_skills(skills)
    matcher.attach(skills, matches)
"""

import logging
import re

from careercompass.skills.taxonomy import TAXONOMY_VERSION, load_taxonomy, normalize
from careercompass.skills.embeddings import load_or_build_index
from careercompass.skills.reranker import get_reranker
from careercompass.skills.llm import DEFAULT_DOMAIN, LLMDecider, NO_MATCH

logger = logging.getLogger("careercompass.matcher")

# ── Decision Thresholds ────────────────────────────────────────
#
# Starting points, not settled values. The design calls for 300-500 hand
# reviewed mappings; tune these against that set by measuring top-1
# accuracy, wrong-automatic-match rate and how much lands in review.

# A reranked candidate at or above this is accepted without an LLM.
ACCEPT_SCORE = 0.72

# ...provided it also leads the runner-up by this much. Two candidates
# scoring 0.75 and 0.74 means the scorer cannot tell them apart, which is
# exactly the case worth spending a model call on.
ACCEPT_MARGIN = 0.05

# Below this the shortlist is noise; no LLM call, straight to no_match.
REVIEW_FLOOR = 0.40

# The two rerankers do not score on the same scale — the lexical one has
# no way to reach a cross-encoder's confidence on a correct-but-reworded
# match, so a single threshold would send almost everything it decides to
# review. Thresholds therefore travel with the scorer, and both sets need
# re-tuning against the reviewed mappings.
SCORER_THRESHOLDS = {
    "lexical": {"accept_score": 0.62, "review_floor": 0.40},
    "cross": {"accept_score": 0.72, "review_floor": 0.45},
}

# Confidence the LLM must report before its pick is accepted outright.
LLM_ACCEPT_CONFIDENCE = 0.70

# Candidates retrieved per term, and how many are kept on the record for
# a reviewer to look at.
TOP_K = 10
KEEP_CANDIDATES = 3

# Evidence lines fed into retrieval alongside the term.
EVIDENCE_LINES = 3

ACCEPTED = "accepted"
NEEDS_REVIEW = "needs_review"
UNMATCHED = "no_match"


def _is_distinctive_one_word_alias(term: str, details: dict) -> bool:
    """Whether a one-word alias carries enough identity to be exact-safe."""
    if len(normalize(term).split()) != 1:
        return False
    surface = details["matched_surface"]
    if any(character.isdigit() or character in "._+#" for character in surface):
        return True
    letters = "".join(character for character in surface if character.isalpha())
    if 3 <= len(letters) <= 8 and letters.isupper():
        return True
    # Product spellings such as GazeboSim are much less ambiguous than
    # ordinary title-cased words such as Node, Access, Spring, or Sketch.
    if re.search(r"[a-z][A-Z]", surface):
        return True

    # Some public taxonomies lowercase acronym aliases (for example "uml").
    # Recover those from the preferred label without trusting an all-caps PDF
    # heading such as "FILTERS" to declare itself an acronym.
    label_words = normalize(details["skill"]["label"]).split()
    initials = "".join(word[0] for word in label_words if word)
    return 3 <= len(initials) <= 8 and normalize(surface) == initials


def _shortlist_with_required(ranked: list, required_skills: list, limit: int) -> list:
    """Keep exact collision claimants visible to the LLM and reviewer."""
    selected = list(ranked[:limit])
    if not required_skills or limit <= 0:
        return selected

    ranked_by_id = {skill["id"]: (skill, score) for skill, score in ranked}
    required_ids = {skill["id"] for skill in required_skills}
    for skill in required_skills:
        pair = ranked_by_id.get(skill["id"])
        if pair is None or any(item[0]["id"] == skill["id"] for item in selected):
            continue
        if len(selected) < limit:
            selected.append(pair)
            continue
        replacement = next(
            (index for index in range(len(selected) - 1, -1, -1)
             if selected[index][0]["id"] not in required_ids),
            None,
        )
        if replacement is not None:
            selected[replacement] = pair
    return selected


def evidence_text(skill: dict, limit: int = EVIDENCE_LINES) -> str:
    """
    Collect the syllabus lines a skill was drawn from.

    This is the "augmented" half of the query. "Java" retrieved on its own
    is ambiguous; "Java" plus "Lab3: Object-oriented programming in Java"
    is not.
    """
    seen = []
    for item in skill.get("evidence", []):
        text = (item.get("text") or "").strip()
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= limit:
            break
    return " ; ".join(seen)


def _record(term: str, skill=None, method: str = "", score: float = 0.0,
            status: str = UNMATCHED, candidates=None, reason: str = "") -> dict:
    """Build one canonical match record."""
    return {
        "original_term": term,
        "canonical_id": skill["id"] if skill else None,
        "canonical_label": skill["label"] if skill else None,
        "taxonomy": skill["source"] if skill else None,
        "taxonomy_version": TAXONOMY_VERSION,
        "match_method": method or "none",
        "match_score": round(float(score), 3),
        "review_status": status,
        "reason": reason,
        "candidates": [
            {"id": candidate["id"], "label": candidate["label"], "score": round(value, 3)}
            for candidate, value in (candidates or [])[:KEEP_CANDIDATES]
        ],
    }


class SkillMatcher:
    """Resolves extracted skill phrases onto canonical taxonomy entries."""

    def __init__(self, taxonomy, index, reranker, decider=None, top_k: int = TOP_K,
                 accept_score: float = ACCEPT_SCORE, accept_margin: float = ACCEPT_MARGIN,
                 review_floor: float = REVIEW_FLOOR):
        if index.embedder is None:
            raise ValueError(
                "This VectorIndex has no embedder attached, so queries cannot be "
                "encoded. Build it through skill_embeddings.load_or_build_index."
            )
        self.taxonomy = taxonomy
        self.index = index
        self.reranker = reranker
        self.decider = decider or LLMDecider(enabled=False)
        self.top_k = top_k
        self.accept_score = accept_score
        self.accept_margin = accept_margin
        self.review_floor = review_floor

    @classmethod
    def build(cls, backend: str = "", reranker: str = "", use_llm=None,
              rebuild: bool = False, domain: str = DEFAULT_DOMAIN,
              **options) -> "SkillMatcher":
        """
        Assemble a matcher from the configured backends.

        Each stage degrades on its own: without sentence-transformers the
        retrieval and reranking fall back to lexical scoring, and without
        an API key the LLM stage is skipped and its cases go to review.

        `domain` tells the LLM stage which document the phrases came from
        — "syllabus" or "job_posting". It changes only how the prompt
        frames the evidence, never the rules or the schema.
        """
        taxonomy = load_taxonomy()
        index = load_or_build_index(taxonomy, backend=backend, rebuild=rebuild)
        scorer = get_reranker(reranker)
        # None lets CC_MATCH_LLM decide. True/False are explicit CLI or API
        # overrides, so --llm and --no-llm remain predictable.
        decider = LLMDecider(enabled=use_llm, domain=domain)
        if decider.enabled and not decider.available:
            logger.warning("LLM stage requested but unavailable: %s",
                           decider.reason_unavailable)

        family = "cross" if scorer.name.startswith("cross") else "lexical"
        thresholds = dict(SCORER_THRESHOLDS[family])
        thresholds.update(options)  # an explicit threshold always wins
        return cls(taxonomy, index, scorer, decider, **thresholds)

    def with_thresholds(self, **overrides) -> "SkillMatcher":
        """
        A matcher differing only in its decision thresholds.

        Shares the taxonomy, vector index, reranker and LLM client rather
        than rebuilding them. Calling build() a second time in one process
        loads a second copy of the embedding model, which on a single GPU
        means the two of them plus a local LLM do not fit — the recheck
        pass exists precisely to run alongside an already-built matcher.
        """
        thresholds = {
            "top_k": self.top_k,
            "accept_score": self.accept_score,
            "accept_margin": self.accept_margin,
            "review_floor": self.review_floor,
        }
        thresholds.update(overrides)
        return SkillMatcher(self.taxonomy, self.index, self.reranker,
                            self.decider, **thresholds)

    def _exact_decision(self, term: str):
        """Classify an alias-index hit as safe exact or context-dependent."""
        details = self.taxonomy.index.lookup_details(term)
        if details is None:
            return None

        # A literal primary label is authoritative even if another record
        # happens to reuse it as an alias.
        if details["matched_kind"] == "label" and details["surface_exact"]:
            details["strong"] = True
            return details

        # Collisions are never safe shortcuts.  A unique preferred label
        # reached through plural/compact key folding remains authoritative.
        if not details["unique"]:
            details["strong"] = False
        elif details["matched_kind"] in ("label", "translated_label"):
            details["strong"] = True
        elif len(normalize(term).split()) > 1:
            details["strong"] = True
        else:
            details["strong"] = _is_distinctive_one_word_alias(term, details)
        return details

    # ── Single term ────────────────────────────────────────────
    def match(self, term: str, evidence: str = "", _vector=None) -> dict:
        """
        Resolve one phrase to a canonical skill.

        Returns:
            A match record with canonical_id, canonical_label, taxonomy,
            taxonomy_version, match_method, match_score, review_status and
            the runner-up candidates that a reviewer would need.
        """
        term = (term or "").strip()
        if not term:
            return _record(term)

        # 1. Exact wording.  Preferred labels, distinctive technology
        #    spellings and multi-word aliases are safe shortcuts.  A plain
        #    one-word alias needs syllabus context because words such as
        #    "communication", "Filters" and "Node" are highly ambiguous.
        exact = self._exact_decision(term)
        if exact is not None and exact["strong"]:
            return _record(term, exact["skill"], "exact_alias", 1.0, ACCEPTED,
                           reason="term matches a taxonomy label or alias")
        contextual_exact = exact["skill"] if exact is not None else None
        contextual_skills = exact["matched_skills"] if exact is not None else []
        if contextual_exact is not None and not evidence.strip():
            return _record(
                term, contextual_exact, "exact_alias", 1.0, NEEDS_REVIEW,
                [(skill, 1.0) for skill in contextual_skills],
                reason="generic one-word alias requires syllabus context",
            )

        # 2. Retrieve. The evidence is weighted behind the term itself by
        #    repeating the term, so a long syllabus line cannot drown out
        #    the phrase actually being matched.
        query = f"{term} . {term} . {evidence}" if evidence else term
        vector = (_vector if _vector is not None
                  else self.index.embedder.encode([query])[0])
        hits = self.index.search(vector, top_k=self.top_k)

        candidates = []
        for skill_id, score in hits:
            skill = self.taxonomy.index.get(skill_id)
            if skill is not None:
                candidates.append((skill, score))
        if contextual_skills:
            # Retrieval can miss short ambiguous words and collision
            # claimants.  Keep every exact candidate in the contextual
            # shortlist, but do not let lexical exactness auto-accept one.
            existing_ids = {skill["id"] for skill, _ in candidates}
            for exact_skill in contextual_skills:
                if exact_skill["id"] not in existing_ids:
                    candidates.append((exact_skill, 1.0))
                    existing_ids.add(exact_skill["id"])
        if not candidates:
            return _record(term, reason="no taxonomy candidates retrieved")

        # 3. Rerank.
        ranked = self.reranker.rerank(term, evidence, candidates)
        llm_ranked = _shortlist_with_required(ranked, contextual_skills, self.top_k)
        review_ranked = _shortlist_with_required(
            ranked, contextual_skills, KEEP_CANDIDATES,
        )
        top_skill, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - runner_up

        # 4. Confident and unambiguous.
        if (contextual_exact is None and top_score >= self.accept_score
                and margin >= self.accept_margin):
            return _record(term, top_skill, "embedding_reranker", top_score, ACCEPTED,
                           ranked, reason=f"leads the runner-up by {margin:.2f}")

        # 5. Too weak to be worth a model call.
        if contextual_exact is None and top_score < self.review_floor:
            return _record(term, None, "embedding_reranker", top_score, UNMATCHED,
                           ranked, reason="best candidate below the review floor")

        # 6. Ambiguous: let the LLM choose from the shortlist, or review.
        if self.decider.available:
            choice = self.decider.decide(term, evidence, llm_ranked)
            if choice is not None:
                if choice["canonical_id"] == NO_MATCH:
                    status = (UNMATCHED
                              if choice["confidence"] >= LLM_ACCEPT_CONFIDENCE
                              else NEEDS_REVIEW)
                    reason = choice["reason"]
                    if status == NEEDS_REVIEW:
                        reason = f"low-confidence no_match: {reason}"
                    return _record(term, None, "llm", choice["confidence"], status,
                                   review_ranked, reason=reason)
                chosen = self.taxonomy.index.get(choice["canonical_id"])
                if chosen is None:
                    # Unreachable unless the taxonomy shifted mid-run; an
                    # id with no record behind it must not be accepted.
                    logger.warning("LLM chose %s, which is not in the taxonomy",
                                   choice["canonical_id"])
                    return _record(term, None, "llm", choice["confidence"], NEEDS_REVIEW,
                                   review_ranked,
                                   reason="selected id is not in the taxonomy")
                status = (ACCEPTED if choice["confidence"] >= LLM_ACCEPT_CONFIDENCE
                          else NEEDS_REVIEW)
                return _record(term, chosen, "llm", choice["confidence"], status,
                               review_ranked, reason=choice["reason"])

        if contextual_exact is not None:
            reason = "generic one-word alias requires contextual confirmation"
        else:
            reason = ("ambiguous: score below accept threshold"
                      if top_score < self.accept_score
                      else f"ambiguous: runner-up within {margin:.2f}")
        return _record(term, top_skill, "embedding_reranker", top_score, NEEDS_REVIEW,
                       review_ranked, reason=reason)

    # ── Whole course ───────────────────────────────────────────
    def match_skills(self, skills: list) -> list:
        """Resolve a course in order, embedding unresolved terms in one batch."""
        results = [None] * len(skills)
        pending = []
        queries = []

        for position, skill in enumerate(skills):
            term = (skill.get("term") or "").strip()
            evidence = evidence_text(skill)

            # Empty, safe-exact, and context-free generic aliases do not
            # need retrieval.  A generic alias with evidence must join the
            # retrieval batch so context can be evaluated.
            exact = self._exact_decision(term) if term else None
            if (not term or (exact is not None and exact["strong"])
                    or (exact is not None and not evidence.strip())):
                results[position] = self.match(term, evidence)
                continue

            query = f"{term} . {term} . {evidence}" if evidence else term
            pending.append((position, term, evidence))
            queries.append(query)

        if queries:
            vectors = self.index.embedder.encode(queries)
            for (position, term, evidence), vector in zip(pending, vectors):
                results[position] = self.match(term, evidence, _vector=vector)

        return results

    @staticmethod
    def attach(skills: list, matches: list) -> list:
        """
        Write the results back onto the extracted skills.

        `canonical` is the compact form the rest of CareerCompass joins
        on; `match` keeps the audit trail — which stage decided, how
        confident it was, and what it was chosen over.
        """
        for skill, match in zip(skills, matches):
            if match["review_status"] == ACCEPTED:
                skill["canonical"] = {
                    "id": match["canonical_id"],
                    "label": match["canonical_label"],
                    "taxonomy": match["taxonomy"],
                }
            else:
                skill["canonical"] = None
            skill["match"] = match
        return skills

    @staticmethod
    def summary(matches: list) -> dict:
        """Counts per review status and per method, for reporting."""
        by_status = {}
        by_method = {}
        for match in matches:
            by_status[match["review_status"]] = by_status.get(match["review_status"], 0) + 1
            by_method[match["match_method"]] = by_method.get(match["match_method"], 0) + 1
        return {
            "total": len(matches),
            "by_status": by_status,
            "by_method": by_method,
            "review_queue": [
                m for m in matches if m["review_status"] == NEEDS_REVIEW
            ],
        }
