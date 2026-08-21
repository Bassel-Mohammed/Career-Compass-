"""
CareerCompass — M2 Student Skill Vector Tests

The guarantee worth testing hardest is that this stage is arithmetic and
nothing more: the same transcript and course → skill map must always produce
identical numbers, because M3 subtracts against them and a student is shown
the result.

The subtler guarantee is that evidence is never double-counted. A syllabus
names one underlying skill through many terms - "derivatives", "integration"
and "limits" all resolve to calculus - and summing them would let a course
that phrases a topic ten ways outweigh one that phrases it once.

Usage:
    python -m tests.test_skill_vector
"""

import sys

from careercompass.skills.vector import (
    LEVEL_FACTOR, apply_quiz_results, build_skill_vector, resolve_retired_ids,
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


def skill(skill_id, label, weight=1.0, level="advanced", status="accepted"):
    return {
        "term": label,
        "canonical": {"id": skill_id, "label": label},
        "weight": weight,
        "level": level,
        "match": {"review_status": status, "canonical_id": skill_id,
                  "canonical_label": label},
    }


def by_id(vector):
    return {s["skill_id"]: s for s in vector["skills"]}


def test_grade_drives_proficiency():
    """The same course content yields proficiency proportional to the grade."""
    course_skills = {"C1": [skill("s:python", "Python")]}
    for grade, expected in (("A", 1.00), ("B", 0.75), ("C", 0.50), ("D", 0.25)):
        v = build_skill_vector([{"course_code": "C1", "grade": grade}], course_skills)
        close(f"grade {grade}", by_id(v)["s:python"]["proficiency"], expected)


def test_level_scales_evidence_not_performance():
    """Level changes how much a course counts, not how well the student did."""
    for level, factor in LEVEL_FACTOR.items():
        cs = {"C1": [skill("s:x", "X", weight=1.0, level=level)]}
        v = build_skill_vector([{"course_code": "C1", "grade": "A"}], cs)
        entry = by_id(v)["s:x"]
        close(f"{level} coverage", entry["coverage"], factor)
        close(f"{level} proficiency", entry["proficiency"], 1.0)


def test_only_accepted_skills_enter():
    """needs_review is a question, not a fact; no_match has no id to join on."""
    cs = {"C1": [
        skill("s:ok", "Kept"),
        skill("s:maybe", "Dropped", status="needs_review"),
        skill("s:no", "Dropped", status="no_match"),
    ]}
    v = build_skill_vector([{"course_code": "C1", "grade": "A"}], cs)
    check("only accepted", sorted(by_id(v)), ["s:ok"])


def test_repeated_terms_in_one_course_do_not_stack():
    """Many terms resolving to one skill count once, at their strongest.

    This is the defect the job ontology hit on 18 August, where summing put
    "monitoring and observability" at 100% of the DevOps path.
    """
    cs = {"C1": [
        skill("s:calc", "calculus", weight=0.6),
        skill("s:calc", "calculus", weight=1.0),
        skill("s:calc", "calculus", weight=0.8),
    ]}
    v = build_skill_vector([{"course_code": "C1", "grade": "A"}], cs)
    entry = by_id(v)["s:calc"]
    check("counted once", entry["course_count"], 1)
    close("strongest weight kept", entry["coverage"], 1.0)


def test_multiple_courses_accumulate_coverage():
    """Separate courses are separate evidence and do stack."""
    cs = {
        "C1": [skill("s:db", "Databases", weight=1.0)],
        "C2": [skill("s:db", "Databases", weight=1.0)],
    }
    v = build_skill_vector(
        [{"course_code": "C1", "grade": "A"}, {"course_code": "C2", "grade": "C"}], cs)
    entry = by_id(v)["s:db"]
    check("two courses", entry["course_count"], 2)
    close("coverage adds", entry["coverage"], 2.0)
    close("proficiency is the mean", entry["proficiency"], 0.75)


def test_weight_biases_the_mean():
    """A course that teaches a skill hard counts more toward proficiency."""
    cs = {
        "C1": [skill("s:x", "X", weight=1.0)],   # A, strong coverage
        "C2": [skill("s:x", "X", weight=0.2)],   # D, barely mentioned
    }
    v = build_skill_vector(
        [{"course_code": "C1", "grade": "A"}, {"course_code": "C2", "grade": "D"}], cs)
    # (1.0*1.0 + 0.2*0.25) / 1.2
    close("weighted mean", by_id(v)["s:x"]["proficiency"], (1.0 + 0.05) / 1.2)


def test_unpassed_courses_are_skipped():
    """A registered or exempted course is not evidence."""
    cs = {"C1": [skill("s:x", "X")]}
    for status, grade in (("Registered", None), ("Exempted", None), ("Pass", "F")):
        v = build_skill_vector(
            [{"course_code": "C1", "grade": grade, "status": status}], cs)
        check(f"{status}/{grade} skipped", v["total_skills"], 0)
        check(f"{status}/{grade} reason", v["courses_skipped"][0]["reason"], "not passed")


def test_alternative_course_codes_resolve():
    """A transcript quotes its own plan's code; the map may hold another."""
    cs = {"A0413301": [skill("s:os", "Operating Systems")]}
    v = build_skill_vector(
        [{"course_code": "0433301", "course_codes": ["0433301", "A0413301"],
          "grade": "A"}], cs)
    check("resolved via alternative", v["total_skills"], 1)


def test_unmapped_course_is_reported_not_silent():
    cs = {"C1": [skill("s:x", "X")]}
    v = build_skill_vector([{"course_code": "C9", "grade": "A"}], cs)
    check("nothing counted", v["courses_counted"], 0)
    check("reported", v["courses_skipped"], [{"course_code": "C9", "reason": "no skill map"}])


def test_quiz_overrides_grades():
    """A quiz measures the skill directly, so it replaces the inference."""
    cs = {"C1": [skill("s:x", "X")]}
    v = build_skill_vector([{"course_code": "C1", "grade": "C"}], cs)
    close("from grades", by_id(v)["s:x"]["proficiency"], 0.5)

    v = apply_quiz_results(v, {"s:x": 0.9})
    entry = by_id(v)["s:x"]
    close("quiz wins", entry["proficiency"], 0.9)
    close("grade value kept", entry["proficiency_from_grades"], 0.5)
    check("evidence", entry["evidence"], "grades+quizzes")
    check("source", v["source"], "grades+quizzes")


def test_quiz_can_add_an_unstudied_skill():
    cs = {"C1": [skill("s:x", "X")]}
    v = apply_quiz_results(
        build_skill_vector([{"course_code": "C1", "grade": "A"}], cs), {"s:new": 0.8})
    entry = by_id(v)["s:new"]
    check("added", entry["evidence"], "quizzes")
    check("no coursework", entry["course_count"], 0)
    check("total updated", v["total_skills"], 2)


def test_no_quizzes_falls_back_to_grades():
    """FR-JS-22: a student who has taken no quiz still has a profile."""
    cs = {"C1": [skill("s:x", "X")]}
    v = apply_quiz_results(build_skill_vector([{"course_code": "C1", "grade": "A"}], cs), {})
    check("source unchanged", v["source"], "grades")


def test_transfer_credit_adds_coverage_without_scoring_zero():
    """Transfer credit is study without a mark, not a mark of zero.

    `_attainment` returns 0.0 for a missing grade, so a transferred course used
    to average into the proficiency mean exactly like a failed one. Measured on
    a mixed profile, 11 of 46 skills came back at proficiency 0.0 because of it.
    The module comment always said transfer credit "contributes coverage
    without attainment"; the arithmetic did not.
    """
    graded = {"course_code": "C1", "grade": "A", "status": "passed"}
    transfer = {"course_code": "C2", "grade": None, "status": "transferred"}
    course_map = {"C1": [skill("s:x", "X")], "C2": [skill("s:x", "X")]}

    v = build_skill_vector([graded, transfer], course_map)
    entry = by_id(v)["s:x"]
    close("an A stays an A", entry["proficiency"], 1.0)
    close("both courses count as study", entry["coverage"], 2.0)
    close("only one carried a mark", entry["graded_coverage"], 1.0)
    check("both courses are counted", v["courses_counted"], 2)

    # A transferred course is credit earned, so it is not "not passed".
    only = build_skill_vector([transfer], {"C2": [skill("s:x", "X")]})
    check("transfer is not skipped", only["courses_skipped"], [])
    entry = by_id(only)["s:x"]
    close("coverage is credited", entry["coverage"], 1.0)
    close("nothing was marked", entry["graded_coverage"], 0.0)
    check("and says so", entry["evidence"], "transfer")

    # A genuinely unfinished course is still excluded, and says which.
    for status in ("registered", "exempted", "withdrawn", "incomplete"):
        v = build_skill_vector([{"course_code": "C1", "grade": None, "status": status}],
                               course_map)
        check(f"{status} is skipped", [s["reason"] for s in v["courses_skipped"]],
              ["not passed"])
        check(f"{status} reason names the status",
              v["courses_skipped"][0]["status"], status)

    # An F is a mark, and it is not credit.
    failed = build_skill_vector([{"course_code": "C1", "grade": "F", "status": "passed"}],
                                course_map)
    check("an F is still skipped", len(failed["courses_skipped"]), 1)


def test_retired_ids_are_repointed_at_load():
    """A merged-away id must not silently fail to join.

    Merging two taxonomy records for one skill retires the loser's id, but rows
    already written still carry it. `remap_retired_skills` repaired the database
    and nothing repaired the JSON artefacts — which is what every API path reads.
    `custom:java` survived there after the 18 August merge, so a student graded
    A in Object Oriented Programming in Java joined against nothing and was
    reported as having a complete Java gap.

    The successor is found the way the database repair finds it: resolve the
    retired *label* through the current alias index, which works because a merge
    keeps the loser's label as an alias.
    """
    from careercompass.skills.taxonomy import Taxonomy, make_skill

    taxonomy = Taxonomy([
        make_skill("esco:java", "Java", "esco", aliases=["Java (computer programming)"]),
        make_skill("custom:docker", "Docker", "custom"),
    ])

    rows = [skill("custom:java", "Java"), skill("custom:docker", "Docker")]
    repointed = resolve_retired_ids(rows, taxonomy, source="test")
    check("one row repointed", repointed, 1)
    check("canonical id follows the merge", rows[0]["canonical"]["id"], "esco:java")
    check("the audit trail follows too", rows[0]["match"]["canonical_id"], "esco:java")
    check("and so does the source name", rows[0]["canonical"]["taxonomy"], "esco")
    check("a live id is untouched", rows[1]["canonical"]["id"], "custom:docker")

    # The whole point: the repointed row now joins to the requirement.
    vector = build_skill_vector([{"course_code": "C1", "grade": "A"}], {"C1": rows})
    check("Java is in the vector under the live id", "esco:java" in by_id(vector), True)

    # An id whose label no longer resolves is left alone rather than guessed at.
    orphan = [skill("custom:gone", "a label no taxonomy has")]
    check("unresolvable is not invented", resolve_retired_ids(orphan, taxonomy), 0)
    check("and is left as it was", orphan[0]["canonical"]["id"], "custom:gone")

    # No taxonomy means no resolution, not a crash: the API degrades to this
    # while the index is still warming.
    check("no taxonomy is a no-op", resolve_retired_ids(rows, None), 0)


def test_deterministic():
    """The same input must serialise identically, every time."""
    import json
    cs = {
        "C1": [skill("s:a", "A", weight=0.9), skill("s:b", "B", weight=0.9)],
        "C2": [skill("s:b", "B", weight=0.9), skill("s:c", "C", weight=0.9)],
    }
    courses = [{"course_code": "C1", "grade": "A"}, {"course_code": "C2", "grade": "B"}]
    first = json.dumps(build_skill_vector(courses, cs), sort_keys=True)
    for _ in range(3):
        check("stable", json.dumps(build_skill_vector(courses, cs), sort_keys=True), first)
    # Row order must not depend on dict insertion order either.
    reordered = json.dumps(build_skill_vector(list(reversed(courses)), cs), sort_keys=True)
    check("order-independent", json.loads(reordered)["skills"],
          json.loads(first)["skills"])


def main():
    test_grade_drives_proficiency()
    test_level_scales_evidence_not_performance()
    test_only_accepted_skills_enter()
    test_repeated_terms_in_one_course_do_not_stack()
    test_multiple_courses_accumulate_coverage()
    test_weight_biases_the_mean()
    test_unpassed_courses_are_skipped()
    test_alternative_course_codes_resolve()
    test_unmapped_course_is_reported_not_silent()
    test_quiz_overrides_grades()
    test_quiz_can_add_an_unstudied_skill()
    test_no_quizzes_falls_back_to_grades()
    test_transfer_credit_adds_coverage_without_scoring_zero()
    test_retired_ids_are_repointed_at_load()
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
