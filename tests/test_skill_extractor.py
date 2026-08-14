"""
CareerCompass — Skill Extractor Tests

Checks the deterministic skill mining over both reference syllabi: that
levels follow the JNQF descriptor, that weights follow the source zone,
and that the known text defects of these PDFs stay filtered out.


Usage:
    python -m tests.test_skill_extractor
    python -m tests.test_skill_extractor "path/to/syllabus.pdf"

"""

import sys
from pathlib import Path
from textwrap import shorten

from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.extractor import _phrases, extract_skills

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROBOTICS_PDF = str(FIXTURES / "robotics_programming.pdf")
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



def extract_and_display(pdf_path: str | Path) -> dict:
    """Extract a PDF's skills, print a readable report, and return all data.

    The returned dictionary remains suitable for assertions, JSON output, or
    further processing.  The ``why`` column is derived from each skill's first
    evidence record; the complete evidence list is preserved in ``skills``.

    Args:
        pdf_path: Path to a text-based course syllabus PDF.

    Returns:
        A dictionary containing the PDF path, parsed syllabus, skill count,
        and extracted skill dictionaries.
    """
    path = Path(pdf_path).expanduser()
    syllabus = parse_syllabus(str(path))
    skills = extract_skills(syllabus)
    result = {
        "pdf_path": str(path.resolve()),
        "syllabus": syllabus,
        "total_skills": len(skills),
        "skills": skills,
    }

    title = syllabus.get("course_title") or "Unknown course"
    code = syllabus.get("course_code") or "no course code"
    print(f"\n{title} ({code})")
    print(f"Source: {path}")
    print(f"Extracted skills: {len(skills)}")

    warnings = syllabus.get("warnings", [])
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    columns = (
        ("#", 3),
        ("Skill", 32),
        ("Level", 12),
        ("Weight", 6),
        ("Sources", 20),
        ("Why extracted", 52),
    )
    header = " | ".join(name.ljust(width) for name, width in columns)
    print(f"\n{header}")
    print("-" * len(header))

    for number, skill in enumerate(skills, start=1):
        evidence = skill.get("evidence", [])
        first_evidence = evidence[0] if evidence else {}
        source = first_evidence.get("source", "unknown")
        location = (
            f"CLO {first_evidence['clo']}"
            if "clo" in first_evidence
            else f"week {first_evidence['week']}"
            if "week" in first_evidence
            else source
        )
        evidence_text = first_evidence.get("text", "")
        why = shorten(
            f"{location}: {evidence_text}",
            width=columns[-1][1],
            placeholder="...",
        )
        values = (
            str(number),
            shorten(skill["term"], width=columns[1][1], placeholder="..."),
            skill["level"],
            f"{skill['weight']:.2f}",
            shorten(
                ", ".join(skill["sources"]),
                width=columns[4][1],
                placeholder="...",
            ),
            why,
        )
        print(" | ".join(value.ljust(width) for value, (_, width) in zip(values, columns)))

    return result


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


def test_text_cleanup():
    """PDF list artifacts are removed without damaging technology names."""
    for marker in ("\uf0b7", "•", "·", "●", "○", "■", "-", "–", "—"):
        check(f"cleanup.marker.{ord(marker):x}",
              _phrases(f"{marker} Environment setup"), ["Environment setup"])
    check("cleanup.no_space_en_dash",
          _phrases("–Client/Server"), ["Client/Server"])
    check("cleanup.no_space_em_dash",
          _phrases("—Client/Server"), ["Client/Server"])
    check("cleanup.asterisk_marker",
          _phrases("* Pointer dereferencing"), ["Pointer dereferencing"])
    check("cleanup.star_args",
          _phrases("*args and **kwargs"), ["*args", "**kwargs"])
    check("cleanup.double_star_kwargs",
          _phrases("**kwargs handling"), ["**kwargs handling"])

    check("cleanup.client_server", _phrases("- Client/Server"), ["Client/Server"])
    check("cleanup.files_io",
          _phrases("Files I/O & Multithreading"), ["Files I/O", "Multithreading"])
    check("cleanup.raster_vector",
          _phrases("image types (raster/vector)"), ["image types", "raster/vector"])
    check("cleanup.c_cpp", _phrases("C/C++"), ["C/C++"])

    check("cleanup.unmatched_open",
          _phrases("Environment setup (OpenCV,"), ["Environment setup OpenCV"])
    check("cleanup.unmatched_close",
          _phrases("NumPy, Matplotlib)"), ["NumPy", "Matplotlib"])

    for heading in ("(Chapter 8)", "Chapter 9", "Chapter 11 & 12",
                    "Chapter 11/12", "(Chapter 11/12)"):
        check(f"cleanup.chapter.{heading}", _phrases(heading), [])
    check("cleanup.chapter_keeps_skill",
          _phrases("or Swing (Chapter 12)"), ["Swing"])
    check("cleanup.chapter_prefix",
          _phrases("Chapter 11 - Interfaces"), ["Interfaces"])

    for heading in ("Mid Exam", "Mid-Term", "Midterm Exam", "Final",
                    "Final Exam", "Final-Exam", "Mid-Semester Exam",
                    "Midterm/Final Exam", "Final Exam / Project",
                    "Comprehensive Review & Final"):
        check(f"cleanup.exam.{heading}", _phrases(heading), [])
    check("cleanup.exam_with_content",
          _phrases("Final Exam: recursion"), ["recursion"])
    check("cleanup.exam_prefix",
          _phrases("Mid Exam - Interfaces"), ["Interfaces"])
    check("cleanup.mid_semester_prefix",
          _phrases("Mid-Semester Exam - Interfaces"), ["Interfaces"])
    check("cleanup.final_exam_prefix",
          _phrases("Final-Exam - Interfaces"), ["Interfaces"])
    for compound in ("Mid-level representation", "Mid-point circle algorithm",
                     "Final-value theorem", "Final-state machine design"):
        check(f"cleanup.exam_prefix_negative.{compound}",
              _phrases(compound), [compound])

    for compound in ("Peer-to-Peer architecture", "Event-Driven Architecture",
                     "human-robot interaction"):
        check(f"cleanup.hyphen.{compound}", _phrases(compound), [compound])
    check("cleanup.balanced_parentheses",
          _phrases("Architecture (SOA)"), ["Architecture", "SOA"])


def main():
    for pdf in (ROBOTICS_PDF, PROBABILITY_PDF):
        if not Path(pdf).exists():
            print(f"❌ Reference PDF not found: {pdf}")
            sys.exit(1)

    test_robotics()
    test_probability()
    test_empty_syllabus()
    test_text_cleanup()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_and_display(sys.argv[1])
    else:
        main()
