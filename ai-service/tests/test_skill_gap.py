"""
CareerCompass — M3 Skill Gap Tests

The guarantees worth testing hardest:

  * the target comes from `required_level`, never from `required_score`.
    Those are different quantities — how deeply the market wants a skill
    versus what share of postings mention it — and confusing them classifies
    almost every requirement as already met.
  * no LLM touches a number. `narrative` is the only generated field and it
    is not produced here.
  * ranking is by what closing a gap is worth, not by the gap alone.
    Otherwise every unstudied skill ties at the top in arbitrary order.

Usage:
    python -m tests.test_skill_gap
"""

import json
import sys

from careercompass.skills.gap import (
    CRITICAL_COVERAGE, IMPORTANT_COVERAGE, LEVEL_COVERAGE, LEVEL_TARGET,
    MODERATE_RATIO, build_skill_gap, demand_band, load_requirements,
    attach_skill_types, top_gaps,
)

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def close(label: str, actual, expected, tol=1e-4):
    global _checks
    _checks += 1
    if abs(actual - expected) > tol:
        _failures.append(f"{label}\n      expected: ~{expected!r}\n      actual:   {actual!r}")


def vector(*pairs, source="grades"):
    """A skill vector from `(skill_id, proficiency)` or `(id, proficiency, coverage)`.

    Coverage defaults to 1.0 — enough evidence for any requirement — so a test
    that only cares about proficiency does not have to think about it.
    """
    skills = []
    for pair in pairs:
        sid, proficiency = pair[0], pair[1]
        coverage = pair[2] if len(pair) > 2 else 1.0
        skills.append({"skill_id": sid, "label": sid, "proficiency": proficiency,
                       "coverage": coverage, "evidence": "grades",
                       "course_count": 1, "courses": []})
    return {"taxonomy_version": "1.0", "source": source, "skills": skills}


def requirement(skill_id, level="advanced", coverage=0.5, skill_type="knowledge",
                required_score=None):
    return {
        "career_path": "Cybersecurity",
        "skill_id": skill_id,
        "skill_label": skill_id,
        "skill_type": skill_type,
        "required_level": level,
        "required_score": 100 * coverage if required_score is None else required_score,
        "coverage": coverage,
    }


def by_id(gap):
    return {r["skill_id"]: r for r in gap["skills"]}


def test_target_comes_from_level_not_score():
    """A rarely-asked-for skill still demands real proficiency.

    required_score has a median near 5 across a path. If it were the target,
    a student with any proficiency at all would clear almost everything.
    """
    for level, target in LEVEL_TARGET.items():
        # coverage 0.02: only 2% of postings mention it, but the level stands.
        g = build_skill_gap(vector(("s:x", 0.0)), [requirement("s:x", level, coverage=0.02)])
        close(f"{level} target", by_id(g)["s:x"]["required_proficiency"], target)
        close(f"{level} gap", by_id(g)["s:x"]["gap"], target)
        check(f"{level} weak", by_id(g)["s:x"]["classification"], "weak")


def test_classification_boundaries():
    target = LEVEL_TARGET["advanced"]
    cases = [
        (target, "strong"),
        (target + 0.1, "strong"),
        (target * MODERATE_RATIO, "moderate"),
        (target * MODERATE_RATIO + 0.01, "moderate"),
        (target * MODERATE_RATIO - 0.01, "weak"),
        (0.0, "weak"),
    ]
    for proficiency, expected in cases:
        g = build_skill_gap(vector(("s:x", proficiency)), [requirement("s:x")])
        check(f"proficiency {proficiency:.3f}", by_id(g)["s:x"]["classification"], expected)


def test_strong_needs_evidence_not_just_a_good_grade():
    """Proficiency alone cannot establish `strong`; M3 needs coverage too.

    For a student with one course the attainment term is constant across every
    skill that course names, so it cancels out of the weighted mean entirely:
    an A gives proficiency 1.0 whether the syllabus built a module on the skill
    or mentioned it once in a week heading. Measured, that reported
    `monitoring and observability` as strong from the single word "Monitors",
    and every strong row in a two-course profile read exactly 1.000.
    """
    target = LEVEL_TARGET["advanced"]
    needed = LEVEL_COVERAGE["advanced"]

    thin = build_skill_gap(vector(("s:x", 1.0, 0.42)), [requirement("s:x")])
    entry = by_id(thin)["s:x"]
    check("a single beginner mention is not strong", entry["classification"], "moderate")
    close("...but proficiency still reads full", entry["current_level"], 1.0)
    close("evidence_coverage is surfaced", entry["evidence_coverage"], 0.42)
    close("so is what was required", entry["required_coverage"], needed)

    thick = build_skill_gap(vector(("s:x", 1.0, needed)), [requirement("s:x")])
    check("enough evidence is strong", by_id(thick)["s:x"]["classification"], "strong")

    # The bar travels with the level asked for, exactly as the target does.
    easy = build_skill_gap(vector(("s:x", 1.0, 0.55)), [requirement("s:x", "beginner")])
    check("a beginner requirement asks less evidence",
          by_id(easy)["s:x"]["classification"], "strong")
    hard = build_skill_gap(vector(("s:x", 1.0, 0.55)), [requirement("s:x", "advanced")])
    check("an advanced one asks more", by_id(hard)["s:x"]["classification"], "moderate")

    # Coverage must not rescue a proficiency that never met the bar.
    poor = build_skill_gap(vector(("s:x", target * 0.5, 5.0)), [requirement("s:x")])
    check("coverage does not substitute for performance",
          by_id(poor)["s:x"]["classification"], "weak")

    # A skill the student does not hold is unaffected by the new gate.
    absent = build_skill_gap(vector(("s:other", 1.0)), [requirement("s:missing")])
    check("unstudied stays weak", by_id(absent)["s:missing"]["classification"], "weak")
    close("and reports no evidence", by_id(absent)["s:missing"]["evidence_coverage"], 0.0)


def test_gap_is_never_negative():
    """Exceeding a requirement leaves nothing to close."""
    g = build_skill_gap(vector(("s:x", 1.0)), [requirement("s:x", "beginner")])
    entry = by_id(g)["s:x"]
    close("no negative gap", entry["gap"], 0.0)
    close("no negative priority", entry["priority"], 0.0)
    check("strong", entry["classification"], "strong")


def test_unstudied_skill_is_a_full_gap():
    g = build_skill_gap(vector(("s:other", 0.9)), [requirement("s:missing")])
    entry = by_id(g)["s:missing"]
    close("current is zero", entry["current_level"], 0.0)
    close("full gap", entry["gap"], LEVEL_TARGET["advanced"])
    check("no evidence", entry["evidence"], None)
    check("no courses", entry["course_count"], 0)


def test_priority_weights_gap_by_demand():
    """A big gap in a skill nobody asks for is not the first thing to fix."""
    reqs = [
        requirement("s:niche", coverage=0.02),   # never studied, rarely asked for
        requirement("s:common", coverage=0.60),  # partly held, widely asked for
    ]
    g = build_skill_gap(vector(("s:common", 0.60)), reqs)
    rows = g["skills"]
    close("niche priority", by_id(g)["s:niche"]["priority"], LEVEL_TARGET["advanced"] * 0.02)
    close("common priority", by_id(g)["s:common"]["priority"],
          (LEVEL_TARGET["advanced"] - 0.60) * 0.60)
    check("common ranks first", rows[0]["skill_id"], "s:common")
    # ...even though the niche skill has the larger raw gap.
    check("niche has the bigger gap",
          by_id(g)["s:niche"]["gap"] > by_id(g)["s:common"]["gap"], True)


def test_soft_skills_rank_last():
    """Soft skills top every path; ranking them first gives everyone the same advice."""
    reqs = [
        requirement("s:soft", coverage=0.95, skill_type="soft"),
        requirement("s:tech", coverage=0.10, skill_type="knowledge"),
    ]
    g = build_skill_gap(vector(), reqs)
    check("technical first", [r["skill_id"] for r in g["skills"]], ["s:tech", "s:soft"])

    dropped = build_skill_gap(vector(), reqs, include_soft=False)
    check("soft excluded", [r["skill_id"] for r in dropped["skills"]], ["s:tech"])
    check("summary follows", dropped["total_requirements"], 1)


def test_top_gaps_excludes_met_and_soft():
    reqs = [
        requirement("s:met", "beginner", coverage=0.5),
        requirement("s:gap", coverage=0.5),
        requirement("s:soft", coverage=0.9, skill_type="soft"),
    ]
    g = build_skill_gap(vector(("s:met", 1.0)), reqs)
    check("only actionable", [r["skill_id"] for r in top_gaps(g)], ["s:gap"])
    check("soft on request",
          sorted(r["skill_id"] for r in top_gaps(g, technical_only=False)),
          ["s:gap", "s:soft"])


def test_summary_counts_every_row():
    reqs = [requirement(f"s:{i}") for i in range(4)]
    g = build_skill_gap(vector(("s:0", 0.9), ("s:1", 0.9), ("s:2", 0.65)), reqs)
    check("summary totals", sum(g["summary"].values()), 4)
    check("strong count", g["summary"]["strong"], 2)
    check("requirements met", g["requirements_met"], g["summary"]["strong"])
    check("total", g["total_requirements"], 4)


def test_no_narrative_is_generated_here():
    """The only LLM field must be absent until something writes it."""
    g = build_skill_gap(vector(("s:x", 0.5)), [requirement("s:x")])
    check("narrative empty", g["narrative"], None)


def test_metadata_carries_through():
    g = build_skill_gap(vector(("s:x", 0.5), source="grades+quizzes"),
                        [requirement("s:x")], career_path="Cybersecurity")
    check("path", g["career_path"], "Cybersecurity")
    check("source", g["source"], "grades+quizzes")
    check("taxonomy version", g["taxonomy_version"], "1.0")

    # The path can also come from the rows themselves.
    inferred = build_skill_gap(vector(), [requirement("s:x")])
    check("path inferred", inferred["career_path"], "Cybersecurity")


def test_missing_skill_type_defaults_to_technical():
    """A row with no type must not be silently treated as soft."""
    req = requirement("s:x", skill_type=None)
    g = build_skill_gap(vector(), [req])
    check("kept when soft excluded",
          len(build_skill_gap(vector(), [req], include_soft=False)["skills"]), 1)
    check("type preserved", by_id(g)["s:x"]["skill_type"], None)


def test_attach_skill_types(tmp=None):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        tax = Path(d) / "taxonomy.jsonl"
        tax.write_text(
            json.dumps({"id": "s:a", "label": "A", "skill_type": "soft"}) + "\n"
            + json.dumps({"id": "s:b", "label": "B", "skill_type": "tool"}) + "\n",
            encoding="utf-8")
        rows = [{"skill_id": "s:a"}, {"skill_id": "s:b", "skill_type": "knowledge"},
                {"skill_id": "s:unknown"}]
        attach_skill_types(rows, tax)
        check("filled", rows[0]["skill_type"], "soft")
        check("existing kept", rows[1]["skill_type"], "knowledge")
        check("unknown stays none", rows[2]["skill_type"], None)


def test_deterministic():
    reqs = [requirement(f"s:{i}", coverage=0.3) for i in range(6)]
    v = vector(("s:0", 0.4), ("s:3", 0.8))
    first = json.dumps(build_skill_gap(v, reqs), sort_keys=True)
    for _ in range(3):
        check("stable", json.dumps(build_skill_gap(v, reqs), sort_keys=True), first)
    shuffled = json.dumps(build_skill_gap(v, list(reversed(reqs))), sort_keys=True)
    check("order-independent", json.loads(shuffled)["skills"], json.loads(first)["skills"])


def test_demand_bands_are_closed_below():
    """The boundary belongs to the higher band, in both directions.

    A skill sitting exactly on 0.25 is critical, not important. Getting this
    backwards moves whole skills between bands on the dashboard for no reason
    a student could ever see, so it is pinned here rather than left to
    whichever comparison someone types next.
    """
    check("exactly critical", demand_band(CRITICAL_COVERAGE), "critical")
    check("just under critical", demand_band(CRITICAL_COVERAGE - 1e-9), "important")
    check("exactly important", demand_band(IMPORTANT_COVERAGE), "important")
    check("just under important", demand_band(IMPORTANT_COVERAGE - 1e-9), "useful")
    check("floor", demand_band(0.02), "useful")
    check("ceiling", demand_band(1.0), "critical")
    # A requirement row with no coverage at all must land somewhere rather
    # than raise: the ontology is data on disk and can predate a field.
    check("missing coverage", demand_band(None), "useful")


def test_rows_carry_their_band_and_the_count_behind_it():
    g = build_skill_gap(vector(("s:a", 0.0)), [
        requirement("s:a", coverage=0.40) | {"posting_count": 72},
    ])
    row = by_id(g)["s:a"]
    check("band", row["demand_band"], "critical")
    check("posting count", row["posting_count"], 72)
    close("importance is the coverage", row["importance"], 0.40)


def test_band_summary_partitions_every_row():
    """Each row lands in exactly one band, and the bands account for all of them.

    The dashboard reads "4 of the 11 things this career insists on" straight
    off this, so a row counted twice or dropped is a wrong number on screen.
    """
    g = build_skill_gap(
        vector(("s:met", 1.0)),
        [
            requirement("s:met", coverage=0.50),   # critical, strong
            requirement("s:c", coverage=0.30),     # critical, weak
            requirement("s:i", coverage=0.15),     # important, weak
            requirement("s:i2", coverage=0.10),    # important, weak (boundary)
            requirement("s:u", coverage=0.03),     # useful, weak
        ],
    )
    bands = g["band_summary"]
    check("critical total", bands["critical"]["total"], 2)
    check("critical strong", bands["critical"]["strong"], 1)
    check("important total", bands["important"]["total"], 2)
    check("useful total", bands["useful"]["total"], 1)
    check("partitions the rows",
          sum(b["total"] for b in bands.values()), g["total_requirements"])
    check("strong agrees with summary",
          sum(b["strong"] for b in bands.values()), g["summary"]["strong"])
    check("weak agrees with summary",
          sum(b["weak"] for b in bands.values()), g["summary"]["weak"])


def test_band_summary_honours_include_soft():
    """Dropping soft requirements must drop them from the band counts too.

    Otherwise the header says eleven critical skills and the list under it
    shows eight, which reads as a bug in the page.
    """
    reqs = [
        requirement("s:tech", coverage=0.40),
        requirement("s:soft", coverage=0.40, skill_type="soft"),
    ]
    with_soft = build_skill_gap(vector(), reqs, include_soft=True)
    without = build_skill_gap(vector(), reqs, include_soft=False)
    check("counted with soft", with_soft["band_summary"]["critical"]["total"], 2)
    check("not counted without", without["band_summary"]["critical"]["total"], 1)
    check("totals still agree",
          sum(b["total"] for b in without["band_summary"].values()),
          without["total_requirements"])


def test_sample_size_is_reported_but_never_required():
    g = build_skill_gap(vector(), [requirement("s:a")], sample_size=184)
    check("carried through", g["sample_size"], 184)
    # An ontology written before the header existed still has to produce a gap.
    check("optional", build_skill_gap(vector(), [requirement("s:a")])["sample_size"], None)


def main():
    test_target_comes_from_level_not_score()
    test_classification_boundaries()
    test_strong_needs_evidence_not_just_a_good_grade()
    test_gap_is_never_negative()
    test_unstudied_skill_is_a_full_gap()
    test_priority_weights_gap_by_demand()
    test_soft_skills_rank_last()
    test_top_gaps_excludes_met_and_soft()
    test_summary_counts_every_row()
    test_demand_bands_are_closed_below()
    test_rows_carry_their_band_and_the_count_behind_it()
    test_band_summary_partitions_every_row()
    test_band_summary_honours_include_soft()
    test_sample_size_is_reported_but_never_required()
    test_no_narrative_is_generated_here()
    test_metadata_carries_through()
    test_missing_skill_type_defaults_to_technical()
    test_attach_skill_types()
    test_deterministic()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
