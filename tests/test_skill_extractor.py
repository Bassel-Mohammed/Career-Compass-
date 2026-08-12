"""
CareerCompass — Skill Extractor Tests

Checks the deterministic skill mining over both reference syllabi: that
levels follow the JNQF descriptor, that weights follow the source zone,
and that the known text defects of these PDFs stay filtered out.

Usage:
    python -m tests.test_skill_extractor
"""

import sys
from pathlib import Path

from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.extractor import extract_skills

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROBOTICS_PDF = str(FIXTURES / "Robotics Syl.pdf")
PROBABILITY_PDF = str(FIXTURES / "probability_and_statistics.pdf")

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def terms(skills: list) -> dict:
    """Index skills by lowercased term."""
    return {s["term"].lower(): s for s in skills}


def test_robotics():
    """Tools, levels and weights over the Robotics syllabus."""
    skills = extract_skills(parse_syllabus(ROBOTICS_PDF))
    found = terms(skills)

    # Concrete tooling has to survive; this is what matches job postings.
    for tool in ("gazebosim harmonic", "rviz 2", "parameter server",
                 "developing ros 2 nodes", "importing 3d models into gazebo"):
        check(f"robotics.has.{tool}", tool in found, True)

    # Level comes from the JNQF descriptor of the CLO the term came from.
    # CLO 2 "Analyze the Robotics Systems Architecture" is marked Skill.
    check("robotics.architecture.level",
          found["robotics systems architecture"]["level"], "intermediate")
    # CLO 4 "Troubleshoot ..." is marked Competency.
    check("robotics.robotic_system.level",
          found["robotic system"]["level"], "advanced")

    # Weight follows the source zone: CLO 1.0, lab 0.8, topic 0.7, desc 0.6.
    check("robotics.clo_weight", found["robotics systems architecture"]["weight"], 1.0)
    check("robotics.lab_weight", found["gazebosim harmonic"]["weight"], 0.8)
    check("robotics.desc_weight", found["computer vision"]["weight"], 0.6)
    # Repeated mentions raise the weight above the zone base.
    check("robotics.repeat_weight", found["actuators"]["weight"] > 0.8, True)
    check("robotics.repeat_sources",
          sorted(found["actuators"]["sources"]), ["description", "topic"])

    # Administrative rows are not skills.
    for noise in ("mid-term", "final exam", "the course", "project",
                  "project presentation and discussion", "components"):
        check(f"robotics.filtered.{noise}", noise in found, False)

    # The Bloom verb states the depth, not the skill, and must be stripped.
    check("robotics.no_leading_verb",
          [t for t in found if t.startswith(("define ", "analyze ", "design "))], [])

    # Topic lines wrap mid-phrase: "... ; Control" / "laws;" is one topic.
    check("robotics.wrapped_topic_rejoined", "control laws" in found, True)
    check("robotics.wrapped_topic_fragment", "control" in found, False)

    # Parenthesized acronyms are skills in their own right.
    check("robotics.acronym", "hri" in found, True)

    # Nothing is canonicalized yet; that is the taxonomy pass.
    check("robotics.canonical_unset",
          all(s["canonical"] is None for s in skills), True)
    # Every skill carries evidence for auditing.
    check("robotics.evidence_present",
          all(len(s["evidence"]) == s["evidence_count"] for s in skills), True)


def test_probability():
    """A theory-only syllabus with no labs still yields its subject skills."""
    skills = extract_skills(parse_syllabus(PROBABILITY_PDF))
    found = terms(skills)

    for topic in ("normal distribution", "binomial distribution",
                  "confidence intervals", "counting rules", "standard deviation"):
        check(f"probability.has.{topic}", topic in found, True)

    # No labs in this course, so nothing may claim a lab source.
    check("probability.no_lab_source",
          any("lab" in s["sources"] for s in skills), False)

    # "Calculate statistical measures. CLO Coverage: 40%" — the coverage
    # note is form bookkeeping appended to the outcome, not a skill.
    check("probability.no_bookkeeping", "clo coverage" in found, False)
    check("probability.statistical_measures", "statistical measures" in found, True)


def test_empty_syllabus():
    """An empty parse yields no skills rather than raising."""
    check("empty.no_skills", extract_skills({}), [])


def main():
    for pdf in (ROBOTICS_PDF, PROBABILITY_PDF):
        if not Path(pdf).exists():
            print(f"❌ Reference PDF not found: {pdf}")
            sys.exit(1)

    test_robotics()
    test_probability()
    test_empty_syllabus()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
