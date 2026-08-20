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
    python -m tests.test_skill_matcher "path/to/syllabus.pdf"
"""

import sys
import json
import tempfile
from pathlib import Path
from textwrap import shorten

from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.extractor import extract_skills
from careercompass.skills.taxonomy import (
    AliasIndex, Taxonomy, key_forms, load_custom_skills, load_taxonomy, make_skill,
    merge_skills, normalize, skill_text, tokens,
)
from careercompass.skills.embeddings import (
    DEFAULT_BGE_BATCH_SIZE, LexicalEmbedder, SentenceTransformerEmbedder,
    VectorIndex, _parse_batch_size,
)
from careercompass.skills.reranker import LexicalReranker, _is_acronym
from careercompass.skills.llm import LLMDecider, NO_MATCH
from careercompass.skills.matcher import (
    ACCEPTED, NEEDS_REVIEW, UNMATCHED, SkillMatcher, evidence_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "syllabi"
ROBOTICS_PDF = str(FIXTURES / "robotics_programming.pdf")

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def match_and_display(
    pdf_path: str | Path,
    matcher: SkillMatcher | None = None,
    *,
    use_llm: bool | None = False,
) -> dict:
    """Match a syllabus PDF, print the decisions, and return structured data.

    A supplied matcher is reused by the test suite.  When this helper builds
    its own matcher, LLM matching is disabled by default so displaying test
    output cannot accidentally make paid API calls.  Pass ``use_llm=True``
    explicitly when an LLM-backed matching report is wanted.
    """
    path = Path(pdf_path).expanduser()
    syllabus = parse_syllabus(str(path))
    skills = extract_skills(syllabus)
    matcher = matcher or SkillMatcher.build(use_llm=use_llm)
    matches = matcher.match_skills(skills)
    matcher.attach(skills, matches)
    summary = matcher.summary(matches)

    result = {
        "pdf_path": str(path.resolve()),
        "syllabus": syllabus,
        "taxonomy": {
            "version": matcher.taxonomy.version,
            "total_skills": len(matcher.taxonomy),
            "retrieval": matcher.index.backend,
            "reranker": matcher.reranker.name,
            "llm": matcher.decider.display_name if matcher.decider.available else None,
        },
        "summary": summary,
        "skills": skills,
        "matches": matches,
    }

    title = syllabus.get("course_title") or "Unknown course"
    code = syllabus.get("course_code") or "no course code"
    print(f"\nMatching results: {title} ({code})")
    print(f"Source: {path}")
    print(
        f"Backend: {matcher.index.backend} retrieval, "
        f"{matcher.reranker.name} reranker"
    )
    print(
        "Summary: "
        f"{summary['total']} total, "
        f"{summary['by_status'].get(ACCEPTED, 0)} accepted, "
        f"{summary['by_status'].get(NEEDS_REVIEW, 0)} need review, "
        f"{summary['by_status'].get(UNMATCHED, 0)} unmatched"
    )

    columns = (
        ("", 1),
        ("Extracted skill", 29),
        ("Canonical match", 29),
        ("Score", 5),
        ("Method", 18),
        ("Why", 40),
    )
    header = " | ".join(name.ljust(width) for name, width in columns)
    print(f"\n{header}")
    print("-" * len(header))

    status_marks = {ACCEPTED: "✓", NEEDS_REVIEW: "?", UNMATCHED: "✗"}
    for skill, match in zip(skills, matches):
        values = (
            status_marks.get(match["review_status"], " "),
            shorten(skill["term"], width=columns[1][1], placeholder="..."),
            shorten(
                match["canonical_label"] or "—",
                width=columns[2][1],
                placeholder="...",
            ),
            f"{match['match_score']:.3f}",
            shorten(match["match_method"], width=columns[4][1], placeholder="..."),
            shorten(match["reason"] or "—", width=columns[5][1], placeholder="..."),
        )
        print(" | ".join(value.ljust(width) for value, (_, width) in zip(values, columns)))

    review_queue = summary["review_queue"]
    if review_queue:
        print(f"\nReview candidates ({len(review_queue)}):")
        for match in review_queue:
            candidates = ", ".join(
                f"{candidate['label']} ({candidate['score']:.3f})"
                for candidate in match["candidates"]
            )
            print(f"  - {match['original_term']}: {candidates or 'no candidates'}")

    print("\n✓ accepted   ? needs review   ✗ no match")
    return result


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

    communication = index.lookup_details("communication")
    check("alias.details_keeps_legacy_hit",
          communication["skill"]["id"], index.lookup("communication")["id"])
    check("alias.details_kind", communication["matched_kind"], "alias")
    check("alias.details_unique", communication["unique"], True)

    collision_index = AliasIndex([
        make_skill("custom:web-css", "web styling", "custom", aliases=["CSS"]),
        make_skill("custom:service-css", "customer support system", "custom",
                   aliases=["CSS"]),
    ])
    collision = collision_index.lookup_details("CSS")
    check("alias.collision_count", collision["collision_count"], 2)
    check("alias.collision_not_unique", collision["unique"], False)
    check("alias.collision_retains_all",
          {skill["id"] for skill in collision["matched_skills"]},
          {"custom:web-css", "custom:service-css"})
    policy_matcher = object.__new__(SkillMatcher)
    policy_matcher.taxonomy = Taxonomy([
        make_skill("custom:web-css", "web styling", "custom", aliases=["CSS"]),
        make_skill("custom:service-css", "customer support system", "custom",
                   aliases=["CSS"]),
    ])
    check("alias.collision_not_strong_exact",
          policy_matcher._exact_decision("CSS")["strong"], False)

    # A canonical label outranks another record reusing the same wording as
    # an alias; label provenance must not be lost in the first-writer index.
    label_collision = AliasIndex([
        make_skill("custom:alias-java", "JVM development", "custom", aliases=["Java"]),
        make_skill("custom:label-java", "Java", "custom"),
    ]).lookup_details("Java")
    check("alias.primary_label_wins", label_collision["skill"]["id"],
          "custom:label-java")


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
    check("embed.batch_size.valid", _parse_batch_size("4"), 4)
    check("embed.batch_size.invalid", _parse_batch_size("invalid"),
          DEFAULT_BGE_BATCH_SIZE)
    check("embed.batch_size.zero", _parse_batch_size(0), DEFAULT_BGE_BATCH_SIZE)

    class RecordingModel:
        def encode(self, texts, **options):
            self.texts = texts
            self.options = options
            return [[0.0] for _ in texts]

    neural = object.__new__(SentenceTransformerEmbedder)
    neural.batch_size = 4
    neural._model = RecordingModel()
    neural.encode(["one", "two"])
    check("embed.batch_size.forwarded", neural._model.options["batch_size"], 4)

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

    for safe_term in ("Java", "Python", "NumPy", "HRI", "ROS2", "GazeboSim",
                      "YOLO", "yolo", "UML", "uml"):
        safe = matcher.match(safe_term, "")
        check(f"match.safe_exact.{safe_term}", safe["review_status"], ACCEPTED)
        check(f"match.safe_exact_method.{safe_term}",
              safe["match_method"], "exact_alias")

    for generic_term in ("communication", "Filters", "Node"):
        generic = matcher.match(generic_term, "")
        check(f"match.generic_review.{generic_term}",
              generic["review_status"], NEEDS_REVIEW)
        check(f"match.generic_retains_suggestion.{generic_term}",
              generic["canonical_id"] is not None, True)

    for uppercase_generic in ("FILTERS", "NODE", "ACCESS", "SPRING"):
        generic = matcher.match(uppercase_generic, "")
        check(f"match.uppercase_generic_review.{uppercase_generic}",
              generic["review_status"], NEEDS_REVIEW)

    contextual = matcher.match("communication", "Network protocol communication frames")
    check("match.generic_context_not_auto_accepted",
          contextual["review_status"], NEEDS_REVIEW)
    check("match.generic_context_is_reranked",
          contextual["match_method"], "embedding_reranker")

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


class _RecordingEmbedder:
    """Delegate embeddings while recording the batches sent to the model."""

    def __init__(self, embedder):
        self._embedder = embedder
        self.calls = []

    def encode(self, texts):
        batch = list(texts)
        self.calls.append(batch)
        return self._embedder.encode(batch)


def test_batch_matching(matcher):
    """Whole-course matching embeds all non-exact terms in one batch."""
    original_embedder = matcher.index.embedder
    recording = _RecordingEmbedder(original_embedder)
    matcher.index.embedder = recording

    skills = [
        {"term": "GazeboSim Harmonic", "evidence": []},
        {"term": "trajectory generation for manipulators", "evidence": []},
        {"term": "communication", "evidence": [
            {"text": "Written communication and presentation skills"},
        ]},
        {"term": "", "evidence": []},
        {"term": "quantum basket weaving", "evidence": []},
    ]
    try:
        matches = matcher.match_skills(skills)
    finally:
        matcher.index.embedder = original_embedder

    check("batch.single_encode_call", len(recording.calls), 1)
    check("batch.contextual_alias_is_unresolved", len(recording.calls[0]), 3)
    check("batch.safe_exact_bypasses_encoding",
          any("GazeboSim Harmonic" in query for query in recording.calls[0]), False)
    check("batch.contextual_alias_is_encoded",
          any(query.startswith("communication . communication")
              for query in recording.calls[0]), True)
    check("batch.preserves_order",
          [match["original_term"] for match in matches],
          [skill["term"] for skill in skills])


def test_collision_matching():
    """Every exact claimant to a colliding alias remains reviewable."""
    collision_skills = [
        make_skill("custom:web-css", "web styling", "custom", aliases=["CSS"]),
        make_skill("custom:service-css", "customer support system", "custom",
                   aliases=["CSS"]),
    ]
    taxonomy = Taxonomy(collision_skills)

    class EmptyEmbedder:
        def encode(self, texts):
            return [[0.0] for _ in texts]

    class EmptyIndex:
        embedder = EmptyEmbedder()

        def search(self, _vector, top_k=10):
            return []

    matcher = SkillMatcher(taxonomy, EmptyIndex(), LexicalReranker())
    result = matcher.match("CSS", "Stylesheet selectors and layout")
    check("match.collision_needs_review", result["review_status"], NEEDS_REVIEW)
    check("match.collision_keeps_all_candidates",
          {candidate["id"] for candidate in result["candidates"]},
          {"custom:web-css", "custom:service-css"})


def test_course_matching(matcher):
    """Matching a whole course, and writing the results back onto the skills."""
    result = match_and_display(ROBOTICS_PDF, matcher)
    skills = result["skills"]
    matches = result["matches"]
    check("course.one_match_each", len(matches), len(skills))

    # canonical is filled only for accepted matches; anything a human still
    # needs to look at stays None so it cannot leak into the gap analysis.
    for skill in skills:
        if skill["match"]["review_status"] == ACCEPTED:
            check(f"course.canonical_set.{skill['term']}", skill["canonical"] is not None, True)
        else:
            check(f"course.canonical_unset.{skill['term']}", skill["canonical"], None)

    accepted = sum(1 for m in matches if m["review_status"] == ACCEPTED)
    reviewed = sum(1 for m in matches if m["review_status"] == NEEDS_REVIEW)
    # Generic aliases intentionally moved from automatic acceptance into
    # review, but the matcher should still find a useful candidate for most
    # extracted terms and accept a substantial core without assistance.
    check("course.accepted_core", accepted >= len(matches) // 3, True)
    check("course.candidate_coverage",
          accepted + reviewed >= (len(matches) * 3) // 4, True)

    summary = result["summary"]
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


class _StubOllamaDecider(LLMDecider):
    """Local provider stub that captures the Ollama request without a server."""

    def _configure_ollama(self):
        self._ollama_ready = True

    def _ollama_request(self, path, payload=None, timeout=None):
        self.last_path = path
        self.last_payload = payload
        return {
            "message": {"content": json.dumps(self.response_payload)},
            "done_reason": "stop",
        }


class _ChoiceDecider:
    """Matcher-level decision stub for confidence routing tests."""

    available = True

    def __init__(self, canonical_id, confidence, reason="stub decision"):
        self.choice = {
            "canonical_id": canonical_id,
            "confidence": confidence,
            "reason": reason,
        }

    def decide(self, _term, _evidence, _candidates):
        return self.choice


def test_matcher_llm_routing(matcher):
    """Only a confident LLM no_match may become a final rejection."""
    original_decider = matcher.decider
    try:
        matcher.decider = _ChoiceDecider(NO_MATCH, 0.45, "possibly unrelated")
        low = matcher.match("communication", "Network protocol communication frames")
        check("match.llm_low_no_match_reviewed", low["review_status"], NEEDS_REVIEW)
        check("match.llm_low_no_match_method", low["match_method"], "llm")
        check("match.llm_low_no_match_reason",
              low["reason"].startswith("low-confidence no_match"), True)

        matcher.decider = _ChoiceDecider(NO_MATCH, 0.91, "not represented")
        high = matcher.match("communication", "Network protocol communication frames")
        check("match.llm_high_no_match_final", high["review_status"], UNMATCHED)
    finally:
        matcher.decider = original_decider


def test_llm_decider():
    """The LLM may only ever return an id from the shortlist it was given."""
    decider = LLMDecider(enabled=False)
    check("llm.disabled_by_default", decider.available, False)
    check("llm.explains_itself", bool(decider.reason_unavailable), True)

    skills = load_custom_skills()
    index = AliasIndex(skills)
    planning = index.lookup("motion planning")
    dynamics = index.lookup("robot dynamics")
    candidates = [(planning, 0.61), (dynamics, 0.55)]

    decider = LLMDecider(
        provider="anthropic",
        enabled=True,
        client=_StubClient({
            "canonical_id": planning["id"], "confidence": 0.93, "reason": "same skill",
        }),
    )

    # A valid pick is passed through, with its confidence clamped.
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

    # The local Ollama path uses schema-constrained JSON and disables Qwen's
    # thinking output so only the small decision object is generated.
    ollama = _StubOllamaDecider(provider="ollama", model="qwen3:8b", enabled=True)
    ollama.response_payload = {
        "canonical_id": planning["id"], "confidence": 0.89, "reason": "same skill",
    }
    choice = ollama.decide("trajectory planning", "", candidates)
    check("ollama.valid_pick", choice["canonical_id"], planning["id"])
    check("ollama.endpoint", ollama.last_path, "/api/chat")
    check("ollama.model", ollama.last_payload["model"], "qwen3:8b")
    check("ollama.no_thinking", ollama.last_payload["think"], False)
    check("ollama.schema_ids",
          ollama.last_payload["format"]["properties"]["canonical_id"]["enum"],
          [planning["id"], dynamics["id"], NO_MATCH])


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

    # Build the deterministic test matcher in memory.  This keeps the suite
    # independent of .env and does not replace the user's persisted BGE index
    # with a lexical test index.
    taxonomy = load_taxonomy()
    embedder = LexicalEmbedder().fit([skill_text(skill) for skill in taxonomy.skills])
    index = VectorIndex.build(taxonomy, embedder)
    matcher = SkillMatcher(
        taxonomy, index, LexicalReranker(), accept_score=0.62, review_floor=0.40,
    )
    print(f"Taxonomy: {len(matcher.taxonomy)} skills  "
          f"retrieval: {matcher.index.backend}  reranker: {matcher.reranker.name}")
    test_matching(matcher)
    test_batch_matching(matcher)
    test_collision_matching()
    test_matcher_llm_routing(matcher)
    test_course_matching(matcher)

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        match_and_display(sys.argv[1])
    else:
        main()
