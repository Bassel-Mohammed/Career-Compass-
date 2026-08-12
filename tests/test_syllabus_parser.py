"""
CareerCompass — Course Syllabus Parser Tests

Golden tests over the two reference syllabi. They differ enough to catch
template assumptions: different faculty, check glyphs vs JNQF descriptor
codes, L/P vs On-campus lecture types, labs vs no labs, and a source
document with genuine numbering defects.

Usage:
    python -m tests.test_syllabus_parser
"""

import sys
from pathlib import Path

from careercompass.parsing.syllabus import parse_syllabus

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROBOTICS_PDF = str(FIXTURES / "Robotics Syl.pdf")
PROBABILITY_PDF = str(FIXTURES / "probability_and_statistics.pdf")

RETURNED_KEYS = {
    "source_file", "course_code", "course_title", "credit_hours",
    "theoretical_hours", "practical_hours", "jnqf_level", "prerequisites",
    "description", "clos", "weeks", "warnings",
}

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def test_returned_shape():
    """The parser returns the agreed fields and nothing else."""
    for pdf in (ROBOTICS_PDF, PROBABILITY_PDF):
        result = parse_syllabus(pdf)
        check(f"shape.{pdf}", set(result), RETURNED_KEYS)
        check(f"shape.{pdf}.clo_keys", set(result["clos"][0]),
              {"number", "text", "jnqf_descriptor", "bloom_verb"})
        check(f"shape.{pdf}.week_keys", set(result["weeks"][0]),
              {"week", "topics", "labs", "clos"})


def test_robotics():
    """Robotics Programming: check glyphs, labs, fragmented schedule tables."""
    result = parse_syllabus(ROBOTICS_PDF)

    check("robotics.source_file", result["source_file"], "Robotics Syl.pdf")
    check("robotics.course_code", result["course_code"], "0432405")
    check("robotics.course_title", result["course_title"], "Robotics Programming")
    check("robotics.credit_hours", result["credit_hours"], 3)
    check("robotics.theoretical_hours", result["theoretical_hours"], 2)
    check("robotics.practical_hours", result["practical_hours"], 1)
    check("robotics.jnqf_level", result["jnqf_level"], 6)
    check("robotics.prerequisites", result["prerequisites"], ["0431201"])

    # Five CLOs, tiered by the position of the check glyph.
    clos = result["clos"]
    check("robotics.clo_count", len(clos), 5)
    check("robotics.clo_tiers",
          [c["jnqf_descriptor"] for c in clos],
          ["knowledge", "skill", "skill", "competency", "skill"])
    check("robotics.clo_verbs",
          [c["bloom_verb"] for c in clos],
          ["Define", "Analyze", "Demonstrate", "Troubleshoot", "Design"])
    check("robotics.clo2_text", clos[1]["text"],
          "Analyze the Robotics Systems Architecture, components, and Kinematics.")

    # The schedule fragments into four separate table objects on page 3.
    weeks = result["weeks"]
    check("robotics.week_count", len(weeks), 15)
    check("robotics.week_numbers", [w["week"] for w in weeks], list(range(1, 16)))

    week3 = weeks[2]
    check("robotics.w3_topics", week3["topics"],
          ["Legged and Wheeled robot’s locomotion",
           "(Concepts & Examples)",
           "Mobile robot Kinematics"])
    # Lab title wraps onto a continuation line and must be rejoined.
    check("robotics.w3_lab", week3["labs"],
          ["Lab3: Getting Started with ROS 2 on Linux"])
    check("robotics.w11_lab", weeks[10]["labs"], ["Lab10: GazeboSim Harmonic"])
    check("robotics.lab_count", sum(len(w["labs"]) for w in weeks), 12)
    check("robotics.w15_clos", weeks[14]["clos"], [1, 2, 3, 4, 5])

    check("robotics.description_start",
          result["description"].startswith("Explore key concepts of artificial intelligence"),
          True)
    check("robotics.warnings", result["warnings"], [])


def test_probability():
    """Probability and Statistics: descriptor codes, no labs, source defects."""
    result = parse_syllabus(PROBABILITY_PDF)

    check("probability.course_code", result["course_code"], "0182102")
    check("probability.course_title", result["course_title"], "Probability and Statistics")
    check("probability.practical_hours", result["practical_hours"], 0)
    check("probability.jnqf_level", result["jnqf_level"], 7)
    # "-" in the prerequisite cell means none.
    check("probability.prerequisites", result["prerequisites"], [])

    # Descriptor columns hold codes such as "K1-P" rather than a check glyph.
    clos = result["clos"]
    check("probability.clo_count", len(clos), 4)
    check("probability.clo_tiers",
          [c["jnqf_descriptor"] for c in clos],
          ["knowledge", "knowledge", "knowledge", "skill"])
    check("probability.clo4_verb", clos[3]["bloom_verb"], "Build")

    weeks = result["weeks"]
    check("probability.no_labs", sum(len(w["labs"]) for w in weeks), 0)
    check("probability.week16_topic", weeks[-1]["topics"], ["Final Exam"])

    # Both warnings are real defects in the source PDF, not parser failures:
    # the schedule cites CLOs 5 and 6 that the CLO table never defines, and
    # week 10's number cell is blank.
    warnings = result["warnings"]
    check("probability.warning_count", len(warnings), 2)
    check("probability.warning_undefined_clos",
          "undefined CLOs: [5, 6]" in warnings[0], True)
    check("probability.warning_week_gap",
          "Week numbering jumps 9 -> 11" in warnings[1], True)


def test_missing_file():
    """A missing PDF raises rather than returning an empty parse."""
    try:
        parse_syllabus("does_not_exist.pdf")
    except FileNotFoundError:
        check("missing_file.raises", True, True)
    else:
        check("missing_file.raises", False, True)


def main():
    for pdf in (ROBOTICS_PDF, PROBABILITY_PDF):
        if not Path(pdf).exists():
            print(f"❌ Reference PDF not found: {pdf}")
            sys.exit(1)

    test_returned_shape()
    test_robotics()
    test_probability()
    test_missing_file()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
