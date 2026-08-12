"""
CareerCompass — Skill Matcher Tests

Covers the RAG taxonomy stage: normalisation and the alias index, source
merging, the embedding index and its staleness guard, reranking, and the
end-to-end matching decisions.

The guarantee worth testing hardest is that nothing in this stage can
invent a canonical id — not the reranker, and not the LLM, whose output is
validated against the shortlist it was given.

Usage:
    python -m tests.test_skill_matcher
"""

import sys
import json
import tempfile
from pathlib import Path

from careercompass.skills.taxonomy import (
    AliasIndex, Taxonomy, key_forms, load_custom_skills, make_skill,
    merge_skills, normalize, skill_text, tokens,
)
from careercompass.skills.embeddings import LexicalEmbedder, VectorIndex
from careercompass.skills.reranker import LexicalReranker, _is_acronym
from careercompass.skills.llm import LLMDecider, NO_MATCH
from careercompass.skills.matcher import (
    ACCEPTED, NEEDS_REVIEW, UNMATCHED, SkillMatcher, evidence_text,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROBOTICS_PDF = str(FIXTURES / "Robotics Syl.pdf")

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


# ── Normalisation ──────────────────────────────────────────────
def test_normalization():
    """Text folding has to collapse the variants a syllabus actually uses."""
    check("norm.case", normalize("GazeboSim Harmonic"), "gazebosim harmonic")
    check("norm.punctuation", normalize("human-robot interaction"), "human robot interaction")
    # The characters that carry meaning inside a technology name survive.
    check("norm.keeps_plus", normalize("C++"), "c++")
    check("norm.keeps_hash", normalize("C#"), "c#")
    check("norm.keeps_dot", normalize("Node.js"), "node.js")
    check("norm.whitespace", normalize("  Robot   Kinematics \n"), "robot kinematics")
    # Arabic diacritics are decoration; ESCO is inconsistent about them.
    check("norm.arabic_marks", normalize("عِلْم"), normalize("علم"))

    # A spelling variant has to share a lookup key with the canonical form.
    check("keys.spacing", bool(key_forms("ROS2") & key_forms("ROS 2")), True)
    check("keys.plural", bool(key_forms("Sensors") & key_forms("sensor")), True)
    check("keys.unrelated", bool(key_forms("Kinematics") & key_forms("Dynamics")), False)

    check("tokens.stopwords", tokens("the basics of robot control"),
          ["basic", "robot", "control"])


# ── Taxonomy ───────────────────────────────────────────────────
def test_custom_taxonomy():
    """The curated seed loads and answers to the wordings syllabi use."""
    skills = load_custom_skills()
    check("custom.loaded", len(skills) > 100, True)
    check("custom.namespaced", all(s["id"].startswith("custom:") for s in skills), True)
    check("custom.sourced", {s["source"] for s in skills}, {"custom"})
    check("custom.unique_ids", len({s["id"] for s in skills}), len(skills))

    index = AliasIndex(skills)
    for term, expected in (
        ("ROS2", "ROS 2"),
        ("Robot Operating System", "ROS 2"),
        ("GazeboSim Harmonic", "Gazebo simulator"),
        ("HRI", "human-robot interaction"),
        ("Rviz 2", "RViz 2"),
        ("sensors", "robot sensors"),
        ("K8s", "Kubernetes"),
        ("normal distribution", "normal distribution"),
    ):
        hit = index.lookup(term)
        check(f"alias.{term}", hit["label"] if hit else None, expected)

    check("alias.miss", index.lookup("quantum basket weaving"), None)


def test_merge():
    """Merging keeps the higher-ranked id and inherits the loser's wording."""
    esco = [make_skill("esco:abc", "robotics", "esco", aliases=["robotic engineering"])]
    custom = [make_skill("custom:robotics", "Robotics", "custom", aliases=["robot science"])]

    merged = merge_skills(custom, esco)
    check("merge.folded", len(merged), 1)
    # ESCO outranks custom, so the public identifier survives...
    check("merge.keeps_esco_id", merged[0]["id"], "esco:abc")
    # ...and the custom wording is preserved as an alias rather than lost.
    check("merge.inherits_alias", "robot science" in merged[0]["aliases"], True)
    check("merge.keeps_own_alias", "robotic engineering" in merged[0]["aliases"], True)

    distinct = merge_skills(
        [make_skill("esco:a", "SLAM", "esco")],
        [make_skill("custom:b", "motion planning", "custom")],
    )
    check("merge.keeps_distinct", len(distinct), 2)

    # A duplicate id would silently overwrite a canonical record downstream.
    try:
        merge_skills(
            [make_skill("esco:dup", "one thing", "esco")],
            [make_skill("esco:dup", "another thing", "esco")],
        )
        check("merge.rejects_duplicate_ids", "no error", "ValueError")
    except ValueError:
        check("merge.rejects_duplicate_ids", "ValueError", "ValueError")


# ── Embeddings ─────────────────────────────────────────────────
def test_embeddings():
    """Vectors must be reproducible, normalised, and self-retrieving."""
    corpus = ["robot kinematics", "motion planning", "network security"]
    embedder = LexicalEmbedder().fit(corpus)
    vectors = embedder.encode(corpus)

    check("embed.shape", vectors.shape, (3, embedder.dim))
    check("embed.normalized",
          all(abs(float((v * v).sum()) - 1.0) < 1e-4 for v in vectors), True)

    # Python's hash() is salted per process; the feature hashing must not
    # be, or a stored index would not match a fresh query vector.
    again = LexicalEmbedder().fit(corpus).encode(corpus)
    check("embed.deterministic", float(abs(vectors - again).max()) < 1e-6, True)

    skills = load_custom_skills()[:60]
    taxonomy = Taxonomy(skills)
    embedder = LexicalEmbedder().fit([skill_text(s) for s in skills])
    index = VectorIndex.build(taxonomy, embedder)
    check("index.size", len(index), len(skills))

    # A skill's own text must retrieve that skill first, or retrieval is
    # broken in a way no threshold can repair.
    target = skills[0]
    hits = index.search(embedder.encode([skill_text(target)])[0], top_k=3)
    check("index.self_retrieval", hits[0][0], target["id"])

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "index.npz"
        index.save(path)

        reloaded = VectorIndex.load(path, fingerprint=taxonomy.fingerprint)
        check("index.roundtrip", reloaded is not None and len(reloaded), len(skills))
        check("index.restores_embedder", reloaded.embedder is not None, True)
        rehit = reloaded.search(reloaded.embedder.encode([skill_text(target)])[0], top_k=1)
        check("index.roundtrip_search", rehit[0][0], target["id"])

        # A taxonomy that changed since the vectors were built must not be
        # served from the stale index.
        check("index.stale_rejected", VectorIndex.load(path, fingerprint="changed"), None)


# ── Reranking ──────────────────────────────────────────────────
def test_reranker():
    """The reranker orders the shortlist and knows an acronym when it sees one."""
    check("rerank.acronym", _is_acronym("HRI", "human-robot interaction"), True)
    check("rerank.acronym_length", _is_acronym("HRI", "human robot"), False)
    check("rerank.not_acronym", _is_acronym("cat", "computer aided design"), False)

    reranker = LexicalReranker()
    index = AliasIndex(load_custom_skills())
    planning = index.lookup("motion planning")
    dynamics = index.lookup("robot dynamics")
    security = index.lookup("network security")

    candidates = [(dynamics, 0.5), (planning, 0.5), (security, 0.5)]
    ranked = reranker.rerank("trajectory generation for the manipulator", "", candidates)
    check("rerank.orders_best_first", ranked[0][0]["id"], planning["id"])
    check("rerank.demotes_unrelated", ranked[-1][0]["id"], security["id"])
    check("rerank.bounded", all(0.0 <= score <= 1.0 for _, score in ranked), True)


# ── Matching ───────────────────────────────────────────────────
def test_matching(matcher):
    """End-to-end decisions over the terms these two syllabi produce."""
    exact = matcher.match("GazeboSim Harmonic", "Lab10: GazeboSim Harmonic")
    check("match.exact_status", exact["review_status"], ACCEPTED)
    check("match.exact_method", exact["match_method"], "exact_alias")
    check("match.exact_score", exact["match_score"], 1.0)
    check("match.exact_label", exact["canonical_label"], "Gazebo simulator")
    check("match.exact_version", exact["taxonomy_version"], matcher.taxonomy.version)

    # Nothing in the taxonomy covers this, and inventing something would
    # be worse than admitting it.
    nonsense = matcher.match("quantum basket weaving", "")
    check("match.nonsense_status", nonsense["review_status"], UNMATCHED)
    check("match.nonsense_id", nonsense["canonical_id"], None)

    check("match.empty_term", matcher.match("", "")["canonical_id"], None)

    # Reworded but recognisable: resolved by retrieval and reranking, not
    # by the alias index.
    reworded = matcher.match("trajectory generation for manipulators",
                             "Week 9: trajectory generation")
    check("match.reworded_method", reworded["match_method"], "embedding_reranker")
    check("match.reworded_status", reworded["review_status"], ACCEPTED)
    check("match.reworded_label", reworded["canonical_label"], "motion planning")

    # A near-tie is exactly the case that must not be auto-accepted.
    ambiguous = matcher.match("wheeled mobile robot navigation", "Mobile robot Kinematics")
    check("match.ambiguous_reviewed", ambiguous["review_status"], NEEDS_REVIEW)
    check("match.ambiguous_keeps_candidates", len(ambiguous["candidates"]) > 1, True)

    # Every id that comes out of the matcher must exist in the taxonomy.
    terms = ["ROS2", "Kinematics", "deep neural network training", "actuators",
             "relational database schema design", "sampling distributions", "HRI"]
    for term in terms:
        result = matcher.match(term, "")
        if result["canonical_id"] is not None:
            check(f"match.real_id.{term}",
                  matcher.taxonomy.index.get(result["canonical_id"]) is not None, True)
        for candidate in result["candidates"]:
            check(f"match.real_candidate.{term}",
                  matcher.taxonomy.index.get(candidate["id"]) is not None, True)

    # The record shape downstream code and the database depend on.
    required = {"original_term", "canonical_id", "canonical_label", "taxonomy",
                "taxonomy_version", "match_method", "match_score",
                "review_status", "candidates"}
    check("match.record_shape", required - set(exact), set())


def test_course_matching(matcher):
    """Matching a whole course, and writing the results back onto the skills."""
    from careercompass.parsing.syllabus import parse_syllabus
    from careercompass.skills.extractor import extract_skills

    skills = extract_skills(parse_syllabus(ROBOTICS_PDF))
    matches = matcher.match_skills(skills)
    check("course.one_match_each", len(matches), len(skills))

    matcher.attach(skills, matches)

    # canonical is filled only for accepted matches; anything a human still
    # needs to look at stays None so it cannot leak into the gap analysis.
    for skill in skills:
        if skill["match"]["review_status"] == ACCEPTED:
            check(f"course.canonical_set.{skill['term']}", skill["canonical"] is not None, True)
        else:
            check(f"course.canonical_unset.{skill['term']}", skill["canonical"], None)

    accepted = sum(1 for m in matches if m["review_status"] == ACCEPTED)
    # These syllabi are what the custom taxonomy was curated against; a
    # sharp drop here means the vocabulary or the thresholds regressed.
    check("course.accepted_majority", accepted >= len(matches) // 2, True)

    summary = matcher.summary(matches)
    check("course.summary_total", summary["total"], len(matches))
    check("course.summary_adds_up", sum(summary["by_status"].values()), len(matches))

    # The result has to survive a JSON round trip; it is written to disk
    # and to a jsonb column.
    check("course.serializable", isinstance(json.dumps(skills, ensure_ascii=False), str), True)

    evidence = evidence_text(skills[0])
    check("course.evidence_text", isinstance(evidence, str) and len(evidence) > 0, True)


# ── LLM stage ──────────────────────────────────────────────────
class _StubResponse:
    """Minimal stand-in for an Anthropic Messages response."""

    class _Block:
        type = "text"

        def __init__(self, text):
            self.text = text

    def __init__(self, payload):
        self.stop_reason = "end_turn"
        self.content = [self._Block(json.dumps(payload))]


class _StubMessages:
    def __init__(self, payload):
        self._payload = payload

    def create(self, **_kwargs):
        return _StubResponse(self._payload)


class _StubClient:
    def __init__(self, payload):
        self.messages = _StubMessages(payload)


def test_llm_decider():
    """The LLM may only ever return an id from the shortlist it was given."""
    decider = LLMDecider()
    check("llm.disabled_by_default", decider.available, False)
    check("llm.explains_itself", bool(decider.reason_unavailable), True)

    skills = load_custom_skills()
    index = AliasIndex(skills)
    planning = index.lookup("motion planning")
    dynamics = index.lookup("robot dynamics")
    candidates = [(planning, 0.61), (dynamics, 0.55)]

    decider = LLMDecider(enabled=False)

    # A valid pick is passed through, with its confidence clamped.
    decider._client = _StubClient({
        "canonical_id": planning["id"], "confidence": 0.93, "reason": "same skill",
    })
    choice = decider.decide("trajectory planning", "", candidates)
    check("llm.valid_pick", choice["canonical_id"], planning["id"])
    check("llm.confidence", choice["confidence"], 0.93)

    # An id outside the shortlist is refused even though the schema enum
    # already forbids it — a fabricated id must never reach the database.
    decider._client = _StubClient({
        "canonical_id": "custom:invented-skill", "confidence": 0.99, "reason": "made up",
    })
    check("llm.rejects_invented_id", decider.decide("anything", "", candidates), None)

    # no_match is a legitimate answer, not a failure.
    decider._client = _StubClient({
        "canonical_id": NO_MATCH, "confidence": 0.8, "reason": "nothing fits",
    })
    check("llm.accepts_no_match",
          decider.decide("anything", "", candidates)["canonical_id"], NO_MATCH)

    # Out-of-range confidence is clamped rather than trusted.
    decider._client = _StubClient({
        "canonical_id": planning["id"], "confidence": 7.5, "reason": "overconfident",
    })
    check("llm.clamps_confidence",
          decider.decide("anything", "", candidates)["confidence"], 1.0)

    # A model that ignores the schema must not crash the pipeline.
    decider._client = _StubClient({"canonical_id": None, "confidence": "high", "reason": ""})
    check("llm.rejects_missing_id", decider.decide("anything", "", candidates), None)


def main():
    for pdf in (ROBOTICS_PDF,):
        if not Path(pdf).exists():
            print(f"❌ Reference PDF not found: {pdf}")
            sys.exit(1)

    test_normalization()
    test_custom_taxonomy()
    test_merge()
    test_embeddings()
    test_reranker()
    test_llm_decider()

    matcher = SkillMatcher.build()
    print(f"Taxonomy: {len(matcher.taxonomy)} skills  "
          f"retrieval: {matcher.index.backend}  reranker: {matcher.reranker.name}")
    test_matching(matcher)
    test_course_matching(matcher)

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
