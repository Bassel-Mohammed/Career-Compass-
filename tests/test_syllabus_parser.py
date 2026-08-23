"""
CareerCompass — Course Syllabus Parser Tests

Golden tests over the reference syllabi. They differ enough to catch template
assumptions: headings inside vs. outside tables, different faculty, check
glyphs vs JNQF descriptor codes, labs vs no labs, and source documents with
genuine numbering defects.

Usage:
    python -m tests.test_syllabus_parser
"""

import sys
from pathlib import Path

from careercompass.parsing.syllabus import parse_syllabus

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "syllabi"
ROBOTICS_PDF = str(FIXTURES / "robotics_programming.pdf")
PROBABILITY_PDF = str(FIXTURES / "probability_and_statistics.pdf")
SYSTEM_ANALYSIS_PDF = str(FIXTURES / "system_analysis_and_design.pdf")
SOFTWARE_ARCHITECTURE_PDF = str(FIXTURES / "software_architecture.pdf")
JAVA_PDF = str(FIXTURES / "object_oriented_programming_in_java.pdf")
COMPUTER_VISION_PDF = str(FIXTURES / "computer_vision.pdf")

ALL_FIXTURES = (
    ROBOTICS_PDF,
    PROBABILITY_PDF,
    SYSTEM_ANALYSIS_PDF,
    SOFTWARE_ARCHITECTURE_PDF,
    JAVA_PDF,
    COMPUTER_VISION_PDF,
)

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

    check("robotics.source_file", result["source_file"], "robotics_programming.pdf")
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


def test_details_heading_outside_table():
    """Word exports with floating section headings retain course metadata."""
    cases = (
        (
            SYSTEM_ANALYSIS_PDF,
            "0412401",
            "System Analysis and Design",
            (3, 3, 0, 7),
            ["0411203"],
            "This course provides students with an in-depth understanding",
        ),
        (
            SOFTWARE_ARCHITECTURE_PDF,
            "0443501",
            "Software Architecture",
            (3, 3, 0, 7),
            ["0442502"],
            "This course offers a comprehensive understanding",
        ),
        (
            JAVA_PDF,
            "0412201",
            "Object-Oriented Programming in Java",
            (3, 3, 0, 6),
            ["0411203"],
            "This course introduces basic Object oriented concepts",
        ),
        (
            COMPUTER_VISION_PDF,
            "0434402",
            "Computer vision",
            (3, 2, 1, 7),
            ["0433401", "0433402"],
            "This course provides a foundational understanding of computer vision",
        ),
    )

    for pdf, code, title, hours, prerequisites, description_start in cases:
        result = parse_syllabus(pdf)
        stem = Path(pdf).stem
        check(f"variant.{stem}.course_code", result["course_code"], code)
        check(f"variant.{stem}.course_title", result["course_title"], title)
        check(
            f"variant.{stem}.hours_and_level",
            (
                result["credit_hours"],
                result["theoretical_hours"],
                result["practical_hours"],
                result["jnqf_level"],
            ),
            hours,
        )
        check(f"variant.{stem}.prerequisites", result["prerequisites"], prerequisites)
        check(
            f"variant.{stem}.description",
            result["description"].startswith(description_start),
            True,
        )
        metadata_warnings = (
            "Course code not found",
            "Course title not found",
            "Course description is empty",
        )
        check(
            f"variant.{stem}.metadata_warnings",
            any(warning.startswith(metadata_warnings) for warning in result["warnings"]),
            False,
        )


def test_missing_file():
    """A missing PDF raises rather than returning an empty parse."""
    try:
        parse_syllabus("does_not_exist.pdf")
    except FileNotFoundError:
        check("missing_file.raises", True, True)
    else:
        check("missing_file.raises", False, True)


def test_malformed_pdfs_raise_valueerror():
    """A document the parser cannot read is a client error, not a server one.

    `pdfplumber` raises `PdfminerException`, which is not a `ValueError`, so it
    escaped the `except ValueError` in both API upload handlers and surfaced as
    HTTP 500 — and as a raw traceback from both CLIs. Everything downstream
    already turns a `ValueError` into the right 422 and the right `❌ Error:`
    line, so the guard normalises onto that type.
    """
    import tempfile

    cases = {
        "plain text named .pdf": b"this is not a pdf at all\n",
        "empty file": b"",
        "truncated pdf": b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrunc",
    }
    for label, payload in cases.items():
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(payload)
            path = handle.name
        try:
            parse_syllabus(path)
        except ValueError:
            check(f"malformed.{label}", True, True)
        except Exception as exc:  # noqa: BLE001 - the point of the test
            check(f"malformed.{label} raised {type(exc).__name__}", False, True)
        else:
            check(f"malformed.{label}", False, True)
        finally:
            Path(path).unlink(missing_ok=True)


def test_decompression_bomb_is_refused():
    """A small PDF must not be allowed to expand without bound.

    PDF content streams are Flate-compressed and repeated drawing operators
    compress extraordinarily well. Measured on this project, a 354 KB file whose
    content stream expands to 106 MB (295:1) drove the API from 2.5 GB to
    12.4 GB of RSS before the kernel killed it. The upload limit does not help:
    it bounds the *compressed* bytes, which is the wrong number.

    The budget is checked before any layout object is built, so this test is
    fast and allocates only the stream itself.
    """
    import tempfile
    import zlib

    raw = (b"BT /F1 8 Tf 10 700 Td (" + b"A" * 40 + b") Tj ET\n") * 400_000
    comp = zlib.compress(raw, 9)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp) + comp + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, start))

    check("bomb.compresses_hard", len(raw) // max(len(out), 1) > 50, True)

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(out)
        path = handle.name
    try:
        parse_syllabus(path)
    except ValueError as exc:
        check("bomb.refused", True, True)
        check("bomb.says_why", "expands" in str(exc), True)
    except Exception as exc:  # noqa: BLE001
        check(f"bomb.refused (raised {type(exc).__name__})", False, True)
    else:
        check("bomb.refused", False, True)
    finally:
        Path(path).unlink(missing_ok=True)


def test_real_syllabi_are_within_budget():
    """The budgets must never refuse a legitimate document."""
    from careercompass.parsing.pdf import max_chars, max_pages, max_stream_bytes

    check("budget.pages_generous", max_pages() >= 100, True)
    check("budget.stream_generous", max_stream_bytes() >= 8 * 1024 * 1024, True)
    check("budget.chars_generous", max_chars() >= 500_000, True)
    for pdf in ALL_FIXTURES:
        result = parse_syllabus(pdf)
        check(f"budget.parses.{Path(pdf).stem}", bool(result["course_code"]), True)


def main():
    for pdf in ALL_FIXTURES:
        if not Path(pdf).exists():
            print(f"❌ Reference PDF not found: {pdf}")
            sys.exit(1)

    test_returned_shape()
    test_robotics()
    test_probability()
    test_details_heading_outside_table()
    test_missing_file()
    test_malformed_pdfs_raise_valueerror()
    test_decompression_bomb_is_refused()
    test_real_syllabi_are_within_budget()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
