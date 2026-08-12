"""
CareerCompass — Candidate Reranking

Retrieval is recall-oriented: it hands back ten plausible taxonomy entries
for a phrase. Reranking is precision-oriented — it looks at the extracted
term, the syllabus evidence behind it and each candidate's full record
together, and decides which one actually says the same thing.

The split matters because the two stages fail differently. An embedding
compares a phrase against thousands of entries cheaply but coarsely, so
"Kinematics" and "Kinetics" land next to each other. A reranker only sees
a handful of pairs, which buys it the budget to compare them properly.

Two backends:

    lexical   token overlap, character similarity, alias containment and
              acronym expansion, scored pairwise. No dependencies.
    cross     BAAI/bge-reranker-v2-m3 through sentence-transformers, the
              cross-encoder the design doc recommends.

Usage:
    from careercompass.skills.reranker import get_reranker

    reranker = get_reranker()
    ranked = reranker.rerank("Developing ROS 2 Nodes", evidence, candidates)
"""

import os
import math
import logging

from careercompass.skills.taxonomy import normalize, tokens, skill_text

logger = logging.getLogger("careercompass.reranker")

DEFAULT_CROSS_ENCODER = "BAAI/bge-reranker-v2-m3"

# How much of the final ordering the retrieval score keeps. The reranker
# is the better judge, but a candidate the retriever loved and the
# reranker merely tolerates is still worth something.
RETRIEVAL_WEIGHT = 0.30


# ── Similarity Parts ───────────────────────────────────────────
def _char_grams(text: str, size: int = 3) -> set:
    """Character n-grams of a space-padded normalised string."""
    padded = f" {normalize(text)} "
    if len(padded) < size:
        return {padded}
    return {padded[i:i + size] for i in range(len(padded) - size + 1)}


def _dice(left: set, right: set) -> float:
    """Sørensen-Dice overlap of two sets."""
    if not left or not right:
        return 0.0
    return 2.0 * len(left & right) / (len(left) + len(right))


def _token_f1(query_tokens: list, label: str) -> float:
    """
    Balanced token overlap between a query and a label.

    F1 rather than plain overlap because both directions matter: a
    candidate that covers every query word but adds five of its own is a
    worse match than one that covers the same words and stops.
    """
    label_tokens = tokens(label)
    if not query_tokens or not label_tokens:
        return 0.0
    shared = len(set(query_tokens) & set(label_tokens))
    if shared == 0:
        return 0.0
    precision = shared / len(set(label_tokens))
    recall = shared / len(set(query_tokens))
    return 2 * precision * recall / (precision + recall)


def _is_acronym(short: str, long: str) -> bool:
    """Whether one string is the initials of the other ("HRI" / "human-robot interaction")."""
    letters = normalize(short).replace(" ", "")
    words = tokens(long, drop_stopwords=True)
    if len(letters) < 2 or len(words) < 2 or len(letters) != len(words):
        return False
    return all(word.startswith(letter) for letter, word in zip(letters, words))


def _labels_of(skill: dict) -> list:
    """Every surface form a skill answers to."""
    labels = [skill["label"], *skill.get("aliases", [])]
    labels.extend(skill.get("labels", {}).values())
    return [label for label in labels if label]


# ── Lexical Reranker ───────────────────────────────────────────
class LexicalReranker:
    """
    Dependency-free pairwise scorer.

    Scores a term against a candidate on three axes — word overlap with
    the closest surface form, character similarity for spelling variants,
    and how much of the syllabus evidence the candidate's description
    accounts for — then adds bounded bonuses for the two patterns raw
    similarity systematically misses: one label containing the other, and
    acronyms.
    """

    name = "lexical"

    def score(self, term: str, evidence: str, skill: dict) -> float:
        """Score one term-candidate pair in the range 0.0 to 1.0."""
        query_tokens = tokens(term)
        query_grams = _char_grams(term)
        query_norm = normalize(term)

        best_f1 = 0.0
        best_dice = 0.0
        bonus = 0.0

        for label in _labels_of(skill):
            best_f1 = max(best_f1, _token_f1(query_tokens, label))
            best_dice = max(best_dice, _dice(query_grams, _char_grams(label)))

            label_norm = normalize(label)
            if query_norm and label_norm:
                if query_norm == label_norm:
                    bonus = max(bonus, 0.15)
                elif query_norm in label_norm or label_norm in query_norm:
                    bonus = max(bonus, 0.08)
            if _is_acronym(term, label) or _is_acronym(label, term):
                bonus = max(bonus, 0.12)

        # Does the surrounding syllabus text talk about the same domain as
        # this candidate? Weak on its own, decisive between two candidates
        # whose labels score identically ("Java" the language, in a course
        # whose evidence mentions programming).
        context = 0.0
        if evidence:
            evidence_tokens = set(tokens(evidence)) - set(query_tokens)
            candidate_tokens = set(tokens(skill_text(skill)))
            if evidence_tokens and candidate_tokens:
                context = len(evidence_tokens & candidate_tokens) / len(evidence_tokens)

        score = 0.55 * best_f1 + 0.30 * best_dice + 0.15 * context + bonus
        return max(0.0, min(1.0, score))

    def rerank(self, term: str, evidence: str, candidates: list) -> list:
        """
        Order candidates best-first.

        Args:
            term: The extracted skill phrase.
            evidence: Surrounding syllabus text, or "".
            candidates: [(skill, retrieval_score)] from the vector index.

        Returns:
            [(skill, score)] sorted by score, highest first.
        """
        ranked = []
        for skill, retrieval_score in candidates:
            pair_score = self.score(term, evidence, skill)
            blended = (1 - RETRIEVAL_WEIGHT) * pair_score + RETRIEVAL_WEIGHT * retrieval_score
            ranked.append((skill, round(min(1.0, max(0.0, blended)), 4)))
        ranked.sort(key=lambda pair: -pair[1])
        return ranked


# ── Cross-Encoder Reranker ─────────────────────────────────────
class CrossEncoderReranker:
    """
    bge-reranker-v2-m3 through sentence-transformers.

    A cross-encoder reads the query and the candidate in one pass instead
    of comparing two independently-produced vectors, which is why it is
    worth the extra model on the ambiguous cases — and why it is only ever
    run over the handful of candidates retrieval already shortlisted.
    """

    def __init__(self, model_name: str = DEFAULT_CROSS_ENCODER):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - depends on install
            raise ImportError(
                "sentence-transformers is not installed. Either "
                "`pip install sentence-transformers` or set "
                "CC_RERANKER=lexical."
            ) from exc

        self.model_name = model_name
        self.name = f"cross:{model_name}"
        self._model = CrossEncoder(model_name)
        self._fallback = LexicalReranker()

    def rerank(self, term: str, evidence: str, candidates: list) -> list:
        if not candidates:
            return []

        query = f"{term} | {evidence}" if evidence else term
        pairs = [[query, skill_text(skill)] for skill, _ in candidates]
        scores = self._model.predict(pairs)

        ranked = []
        for (skill, retrieval_score), raw in zip(candidates, scores):
            # bge-reranker emits logits; squash them into 0..1 so the
            # matcher's thresholds mean the same thing for both backends.
            # The clamp keeps a confidently negative logit from overflowing.
            pair_score = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, float(raw)))))
            blended = (1 - RETRIEVAL_WEIGHT) * pair_score + RETRIEVAL_WEIGHT * retrieval_score
            ranked.append((skill, round(min(1.0, max(0.0, blended)), 4)))
        ranked.sort(key=lambda pair: -pair[1])
        return ranked


def get_reranker(backend: str = ""):
    """
    Build the reranker to use.

    Args:
        backend: "lexical", "cross", or "" / "auto" to read CC_RERANKER
            and fall back to lexical when the cross-encoder is unavailable.
    """
    backend = (backend or os.getenv("CC_RERANKER", "auto")).lower()

    if backend in ("cross", "bge", "cross-encoder"):
        return CrossEncoderReranker(os.getenv("CC_RERANKER_MODEL", DEFAULT_CROSS_ENCODER))

    if backend == "auto":
        try:
            reranker = CrossEncoderReranker(
                os.getenv("CC_RERANKER_MODEL", DEFAULT_CROSS_ENCODER)
            )
            logger.info("Using %s for reranking", reranker.name)
            return reranker
        except ImportError:
            logger.info("sentence-transformers unavailable; using lexical reranking")

    return LexicalReranker()
