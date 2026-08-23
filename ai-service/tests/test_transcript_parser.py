"""
CareerCompass — Academic Plan / Transcript Parser Tests

Covers the two ways this parser has silently lost an entire plan.

Both defects returned wrong data rather than raising, which is what makes
them worth pinning:

  * a course code regex anchored to a leading zero rejected every row of the
    Cyber Security edition-2 plan, whose codes are letter-prefixed. The parser
    returned zero courses and no error.
  * some plans' PDF text layer carries no spaces, so the category name arrived
    as "UniversityRequirementCompulsory". Any caller filtering on the spaced
    form dropped every course in that plan.

The real plan PDFs cannot be fixtures: they carry a student's name, ID,
advisor and full grade history, and are git-ignored. These tests therefore
drive the row-level helpers directly, which is where both defects lived.

Usage:
    python -m tests.test_transcript_parser
"""

import sys

from careercompass.parsing.transcript import (
    COURSE_CODE_RE,
    _extract_section_info,
    _is_data_row,
    _is_section_header,
    _normalise_category,
)

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def test_course_codes():
    """Both numbering schemes are accepted; non-codes still rejected."""
    for code in ("0161101", "0413403", "0182102"):
        check(f"plain code {code}", bool(COURSE_CODE_RE.match(code)), True)

    # The edition-2 plans prefix with a letter. Rejecting these returned an
    # empty plan with no error.
    for code in ("A0161101", "A0413301", "A0434505"):
        check(f"prefixed code {code}", bool(COURSE_CODE_RE.match(code)), True)

    for junk in ("161101", "0161101X", "AB0161101", "", "Course Code", "20241",
                 "a0161101", "00161101"):
        check(f"rejects {junk!r}", bool(COURSE_CODE_RE.match(junk)), False)


def test_data_rows():
    """A course row is recognised under either scheme."""
    plain = ["0182102", "Probability and Statistics", "", "3", "B+", "Pass"]
    prefixed = ["A0182102", "Probability and Statistics", "", "3", "", ""]
    check("plain row", _is_data_row(plain), True)
    check("prefixed row", _is_data_row(prefixed), True)
    check("header row is not data", _is_data_row(["Course Code", "Course Name", "", "Crd"]), False)
    check("short row is not data", _is_data_row(["0182102", "x"]), False)


def test_section_headers_both_spacings():
    """Header detection survives a text layer that carries no spaces."""
    spaced = ["Faculty Requirement Compulsory : ( 18 ) Hour / Hours", None, None,
              "Earned : ( 18 ) Hour / Hours"]
    squashed = ["FacultyRequirementCompulsory:(18)Hour/Hours", None, None,
                "Earned:(18)Hour/Hours"]
    check("spaced header", _is_section_header(spaced), True)
    check("unspaced header", _is_section_header(squashed), True)
    check("course row is not a header", _is_section_header(
        ["0182102", "Probability and Statistics", "", "3"]), False)


def test_category_name_normalisation():
    """The same category yields the same name whichever way the PDF extracts."""
    pairs = [
        ("UniversityRequirementCompulsory", "University Requirement Compulsory"),
        ("FacultyRequirementCompulsory", "Faculty Requirement Compulsory"),
        ("MajorRequirementOptional", "Major Requirement Optional"),
        ("SupportiveRequirementCompulsory", "Supportive Requirement Compulsory"),
        ("OrientationRequirementCompulsory", "Orientation Requirement Compulsory"),
    ]
    for squashed, expected in pairs:
        check(f"normalise {squashed}", _normalise_category(squashed), expected)
        # Already-spaced names must pass through untouched.
        check(f"idempotent {expected}", _normalise_category(expected), expected)

    check("empty name", _normalise_category(""), "")


def test_section_info_matches_across_spacings():
    """Hours and the category name agree whichever spacing the plan uses."""
    spaced = _extract_section_info(
        ["Major Requirement Compulsory : ( 43 ) Hour / Hours", None, None,
         "Earned : ( 40 ) Hour / Hours"])
    squashed = _extract_section_info(
        ["MajorRequirementCompulsory:(43)Hour/Hours", None, None,
         "Earned:(40)Hour/Hours"])

    check("spaced name", spaced["category_name"], "Major Requirement Compulsory")
    check("unspaced name", squashed["category_name"], "Major Requirement Compulsory")
    check("names agree", spaced["category_name"], squashed["category_name"])
    check("required hours", squashed["required_hours"], 43)
    check("passed hours", squashed["passed_hours"], 40)


def main():
    test_course_codes()
    test_data_rows()
    test_section_headers_both_spacings()
    test_category_name_normalisation()
    test_section_info_matches_across_spacings()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
