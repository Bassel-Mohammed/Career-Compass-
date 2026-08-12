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

from careercompass.skills.taxonomy import TAXONOMY_VERSION, load_taxonomy
from careercompass.skills.embeddings import load_or_build_index
from careercompass.skills.reranker import get_reranker
from careercompass.skills.llm import LLMDecider, NO_MATCH

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
    def build(cls, backend: str = "", reranker: str = "", use_llm: bool = False,
              rebuild: bool = False, **options) -> "SkillMatcher":
        """
        Assemble a matcher from the configured backends.

        Each stage degrades on its own: without sentence-transformers the
        retrieval and reranking fall back to lexical scoring, and without
        an API key the LLM stage is skipped and its cases go to review.
        """
        taxonomy = load_taxonomy()
        index = load_or_build_index(taxonomy, backend=backend, rebuild=rebuild)
        scorer = get_reranker(reranker)
        decider = LLMDecider(enabled=True) if use_llm else LLMDecider(enabled=False)
        if use_llm and not decider.available:
            logger.warning("LLM stage requested but unavailable: %s",
                           decider.reason_unavailable)

        family = "cross" if scorer.name.startswith("cross") else "lexical"
        thresholds = dict(SCORER_THRESHOLDS[family])
        thresholds.update(options)  # an explicit threshold always wins
        return cls(taxonomy, index, scorer, decider, **thresholds)

    # ── Single term ────────────────────────────────────────────
    def match(self, term: str, evidence: str = "") -> dict:
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

        # 1. Exact alias — the taxonomy already knows this wording.
        exact = self.taxonomy.index.lookup(term)
        if exact is not None:
            return _record(term, exact, "exact_alias", 1.0, ACCEPTED,
                           reason="term matches a taxonomy label or alias")

        # 2. Retrieve. The evidence is weighted behind the term itself by
        #    repeating the term, so a long syllabus line cannot drown out
        #    the phrase actually being matched.
        query = f"{term} . {term} . {evidence}" if evidence else term
        vector = self.index.embedder.encode([query])[0]
        hits = self.index.search(vector, top_k=self.top_k)

        candidates = []
        for skill_id, score in hits:
            skill = self.taxonomy.index.get(skill_id)
            if skill is not None:
                candidates.append((skill, score))
        if not candidates:
            return _record(term, reason="no taxonomy candidates retrieved")

        # 3. Rerank.
        ranked = self.reranker.rerank(term, evidence, candidates)
        top_skill, top_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - runner_up

        # 4. Confident and unambiguous.
        if top_score >= self.accept_score and margin >= self.accept_margin:
            return _record(term, top_skill, "embedding_reranker", top_score, ACCEPTED,
                           ranked, reason=f"leads the runner-up by {margin:.2f}")

        # 5. Too weak to be worth a model call.
        if top_score < self.review_floor:
            return _record(term, None, "embedding_reranker", top_score, UNMATCHED,
                           ranked, reason="best candidate below the review floor")

        # 6. Ambiguous: let the LLM choose from the shortlist, or review.
        if self.decider.available:
            choice = self.decider.decide(term, evidence, ranked[:self.top_k])
            if choice is not None:
                if choice["canonical_id"] == NO_MATCH:
                    return _record(term, None, "llm", choice["confidence"], UNMATCHED,
                                   ranked, reason=choice["reason"])
                chosen = self.taxonomy.index.get(choice["canonical_id"])
                if chosen is None:
                    # Unreachable unless the taxonomy shifted mid-run; an
                    # id with no record behind it must not be accepted.
                    logger.warning("LLM chose %s, which is not in the taxonomy",
                                   choice["canonical_id"])
                    return _record(term, None, "llm", choice["confidence"], NEEDS_REVIEW,
                                   ranked, reason="selected id is not in the taxonomy")
                status = (ACCEPTED if choice["confidence"] >= LLM_ACCEPT_CONFIDENCE
                          else NEEDS_REVIEW)
                return _record(term, chosen, "llm", choice["confidence"], status,
                               ranked, reason=choice["reason"])

        return _record(term, top_skill, "embedding_reranker", top_score, NEEDS_REVIEW,
                       ranked,
                       reason=("ambiguous: score below accept threshold"
                               if top_score < self.accept_score
                               else f"ambiguous: runner-up within {margin:.2f}"))

    # ── Whole course ───────────────────────────────────────────
    def match_skills(self, skills: list) -> list:
        """Resolve every extracted skill of a course, in order."""
        return [self.match(skill["term"], evidence_text(skill)) for skill in skills]

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
