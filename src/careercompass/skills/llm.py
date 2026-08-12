"""
CareerCompass — Constrained LLM Selection (Claude)

The last stage of the RAG taxonomy pipeline, and the only one that calls a
model. It runs on the narrow band of terms where retrieval and reranking
disagreed or hedged: the top candidate is plausible but not clearly right.

The constraint is the whole point. The model never writes an identifier —
it is handed the shortlisted candidates and a JSON schema whose
canonical_id is an enum of exactly those ids plus "no_match", so a
hallucinated taxonomy id is not a thing it can emit. Everything the model
knows about the vocabulary comes from the retrieved records; that is what
makes this retrieval-augmented rather than a guess.

Disabled by default. Enable with CC_MATCH_LLM=1 and an ANTHROPIC_API_KEY,
or pass --llm to the matching CLI.

Usage:
    from careercompass.skills.llm import LLMDecider

    decider = LLMDecider()
    if decider.available:
        choice = decider.decide(term, evidence, candidates)
"""

import os
import json
import logging

logger = logging.getLogger("careercompass.llm")

# Opus 5 is the default because a wrong canonical id silently corrupts
# every gap analysis built on it; set CC_MATCH_MODEL=claude-haiku-4-5 to
# trade some of that accuracy for cost on a large backfill.
DEFAULT_MODEL = "claude-opus-5"

NO_MATCH = "no_match"

SYSTEM_PROMPT = """You resolve course-syllabus skill phrases onto a fixed skill taxonomy for CareerCompass, a system that compares what a university course teaches against what job postings ask for.

You are given one phrase extracted from a syllabus, the syllabus text it came from, and a shortlist of taxonomy entries retrieved for it. Select the entry that names the same skill.

Rules:
- Choose an entry only when it means the same skill as the phrase, not merely a related or broader topic. "Kinematics" is not "Dynamics"; "ROS 2 node development" is not "software engineering".
- A different wording for the same skill is a match ("HRI" and "human-robot interaction"; "GazeboSim Harmonic" and "Gazebo simulator").
- An entry that is one level broader is acceptable only when no more specific entry is shortlisted and the phrase clearly falls inside it.
- Return no_match when nothing on the shortlist fits. An honest no_match is more useful than a wrong id: unmatched terms go to human review, wrong ids do not.
- confidence is your probability that the selected entry is correct, from 0.0 to 1.0. Report it honestly; a low confidence routes the term to review.
- reason is one sentence naming the evidence you used."""


def _candidate_block(candidates: list) -> str:
    """Render the shortlist the model must choose from."""
    lines = []
    for position, (skill, score) in enumerate(candidates, start=1):
        parts = [f"{position}. id: {skill['id']}", f"   label: {skill['label']}"]
        if skill.get("aliases"):
            parts.append(f"   also called: {', '.join(skill['aliases'][:8])}")
        if skill.get("description"):
            parts.append(f"   description: {skill['description'][:280]}")
        parts.append(f"   source: {skill['source']} | retrieval score: {score:.3f}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


class LLMDecider:
    """
    Claude, constrained to the retrieved candidate ids.

    Constructing this never raises: if the SDK is missing, the key is
    unset, or the feature is switched off, `available` is False and the
    matcher simply routes ambiguous terms to manual review instead.
    """

    def __init__(self, model: str = "", enabled=None):
        self.model = model or os.getenv("CC_MATCH_MODEL", DEFAULT_MODEL)
        self.reason_unavailable = ""
        self._client = None

        if enabled is None:
            enabled = os.getenv("CC_MATCH_LLM", "").lower() in ("1", "true", "yes")
        if not enabled:
            self.reason_unavailable = "LLM stage disabled (set CC_MATCH_LLM=1 or pass --llm)"
            return

        try:
            import anthropic
        except ImportError:
            self.reason_unavailable = "anthropic SDK not installed (pip install anthropic)"
            return

        try:
            # The SDK resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or a
            # stored `ant auth login` profile on its own.
            self._client = anthropic.Anthropic()
        except Exception as exc:  # pragma: no cover - depends on environment
            self.reason_unavailable = f"no Anthropic credentials: {exc}"
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def decide(self, term: str, evidence: str, candidates: list):
        """
        Ask the model to pick one candidate id, or no_match.

        Args:
            term: The extracted skill phrase.
            evidence: Syllabus text the phrase came from.
            candidates: [(skill, retrieval_score)] shortlist, best first.

        Returns:
            {"canonical_id", "confidence", "reason"} where canonical_id is
            always one of the given ids or "no_match" — or None when the
            call could not be made.
        """
        if not self.available or not candidates:
            return None

        allowed = [skill["id"] for skill, _ in candidates]
        schema = {
            "type": "object",
            "properties": {
                "canonical_id": {
                    "type": "string",
                    # The enum is the guardrail: an id outside the
                    # shortlist is not representable in the response.
                    "enum": allowed + [NO_MATCH],
                    "description": "The id of the matching taxonomy entry, or no_match.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Probability from 0.0 to 1.0 that the selection is correct.",
                },
                "reason": {
                    "type": "string",
                    "description": "One sentence justifying the selection.",
                },
            },
            "required": ["canonical_id", "confidence", "reason"],
            "additionalProperties": False,
        }

        prompt = (
            f"Extracted phrase: {term}\n"
            f"Syllabus evidence: {evidence or '(none)'}\n\n"
            f"Taxonomy candidates:\n\n{_candidate_block(candidates)}\n\n"
            f"Which candidate names the same skill as the extracted phrase?"
        )

        try:
            response = self._client.messages.create(
                model=self.model,
                # Thinking is on by default on current models and shares
                # this budget with the answer, so leave room for both.
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("LLM selection failed for %r: %s", term, exc)
            return None

        # Safety classifiers can decline a request; the call still returns
        # 200 with an empty content list, so check before reading it.
        if getattr(response, "stop_reason", "") == "refusal":
            logger.warning("LLM declined to resolve %r", term)
            return None
        if getattr(response, "stop_reason", "") == "max_tokens":
            logger.warning("LLM response for %r was truncated; sending to review", term)
            return None

        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            choice = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM returned unparsable output for %r: %s", term, text[:200])
            return None

        canonical_id = choice.get("canonical_id")
        # Belt and braces: the schema enum already forbids this, but a
        # fabricated id must never reach the database.
        if canonical_id != NO_MATCH and canonical_id not in allowed:
            logger.warning("LLM returned an id outside the shortlist for %r: %s",
                           term, canonical_id)
            return None

        confidence = choice.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "canonical_id": canonical_id,
            "confidence": round(confidence, 3),
            "reason": str(choice.get("reason", ""))[:300],
        }
