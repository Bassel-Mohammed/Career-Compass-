"""
CareerCompass — Academic Plan PDF Parser

Extracts structured course data and student metadata from English MEU
academic plan PDFs using pdfplumber.

Features:
    - Extracts student metadata (Name, ID, GPA, Rating, Plan/Passed/Remaining Hours)
    - Requirement category classification (University, Faculty, Major, Supportive, Orientation)
    - Grade normalization, point conversion, and strength classification
    - Structured JSON output export

Usage:
    from careercompass.parsing.transcript import parse_academic_plan
    result = parse_academic_plan("CS_AI_plan_mohammed_EN.pdf")
"""

import re
import json
import pdfplumber  # noqa: F401  (PDF type annotation on _extract_metadata)
from pathlib import Path

from careercompass.parsing.pdf import open_pdf, page_texts
from careercompass.parsing.grades import (
    normalize_grade,
    grade_to_points,
    classify_grade,
)

# ── Regex Patterns ─────────────────────────────────────────────

# Newer plan editions prefix the course code with a letter: the Cyber Security
# edition-2 plan uses A0161101 where the older plans use 0161101. Without the
# optional prefix every row of such a plan fails _is_data_row and the parser
# returns zero courses with no error at all.
COURSE_CODE_RE = re.compile(r"^[A-Z]?0\d{6}$")
SEMESTER_RE = re.compile(r"^20\d{3}$")
SECTION_KEYWORDS = ["Requirement", "Orientation", "Supportive"]
HEADER_KEYWORDS = ["Course Code", "Course\nCode"]


# ── Row Classification ─────────────────────────────────────────

def _is_section_header(row: list) -> bool:
    """Check if a row is a requirement category header.

    Some plans' PDF text layer carries no spaces at all, yielding
    "UniversityRequirementCompulsory" rather than the spaced form, so the
    keywords are matched against both.
    """
    for cell in row:
        if not cell:
            continue
        text = str(cell)
        squashed = text.replace(" ", "")
        if any(kw in text or kw in squashed for kw in SECTION_KEYWORDS):
            return True
    return False


def _is_column_header(row: list) -> bool:
    """Check if a row is a column header row."""
    for cell in row:
        if cell and any(kw in str(cell) for kw in HEADER_KEYWORDS):
            return True
    return False


def _is_empty_row(row: list) -> bool:
    """Check if a row is entirely empty or None."""
    return all(
        cell is None or (isinstance(cell, str) and not cell.strip())
        for cell in row
    )


def _is_data_row(row: list) -> bool:
    """Check if a row contains a course record."""
    if not row or len(row) < 4:
        return False
    c0 = str(row[0]).strip() if row[0] else ""
    return bool(COURSE_CODE_RE.match(c0))


# ── Section Header Parsing ────────────────────────────────────

CATEGORY_WORDS = ("University", "Faculty", "Major", "Supportive", "Orientation",
                  "Requirement", "Compulsory", "Optional")


def _normalise_category(name: str) -> str:
    """Restore spacing in category names from plans whose text layer has none.

    "UniversityRequirementCompulsory" and "University Requirement Compulsory"
    are the same category. Callers filter on the name, so without this a plan
    that extracts unspaced silently contributes no courses to that filter.
    """
    if " " in name or not name:
        return name
    spaced = name
    for word in CATEGORY_WORDS:
        spaced = spaced.replace(word, f" {word}")
    return " ".join(spaced.split())


def _extract_section_info(row: list) -> dict:
    """Extract category name and required/passed hours from a section header row."""
    left = str(row[0]) if row[0] else ""
    right = str(row[3]) if len(row) > 3 and row[3] else ""

    category_name = _normalise_category(
        left.split(":")[0].strip() if ":" in left else left.strip()
    )
    required_hours = 0
    passed_hours = 0

    req_match = re.search(r"\(\s*(\d+)\s*\)", left)
    if req_match:
        required_hours = int(req_match.group(1))

    earned_match = re.search(r"\(\s*(\d+)\s*\)", right)
    if earned_match:
        passed_hours = int(earned_match.group(1))

    return {
        "category_name": category_name,
        "required_hours": required_hours,
        "passed_hours": passed_hours,
    }


# ── Course Data Extraction ────────────────────────────────────

def _extract_course(row: list) -> dict:
    """Extract a single course record from an English data row."""
    course_code = str(row[0]).strip() if row[0] else ""
    course_name = str(row[1]).strip().replace("\n", " ") if len(row) > 1 and row[1] else ""
    prerequisite_raw = str(row[2]).strip() if len(row) > 2 and row[2] else ""
    
    credit_hours = 0
    if len(row) > 3 and row[3]:
        ch_match = re.search(r"\d+", str(row[3]))
        if ch_match:
            credit_hours = int(ch_match.group(0))

    grade_raw = str(row[4]).strip() if len(row) > 4 and row[4] else None
    s1 = str(row[5]).strip() if len(row) > 5 and row[5] else ""
    s2 = str(row[6]).strip() if len(row) > 6 and row[6] else ""
    semester_raw = str(row[8]).strip() if len(row) > 8 and row[8] else ""
    marker = str(row[7]).strip() if len(row) > 7 and row[7] else ""

    # Status mapping
    if s2 in ["Equivelant", "Equivalent"] or s1 in ["Equivelant", "Equivalent"]:
        status = "transferred"
    elif s2 == "Exempted" or s1 == "Exempted":
        status = "exempted"
    elif s1 == "Pass" or (grade_raw and grade_raw != "None"):
        status = "passed"
    elif s2 == "Registered" or s1 == "Registered" or marker == "X":
        status = "in_progress"
    else:
        status = "not_registered"

    # Prerequisite codes
    prerequisite = None
    if prerequisite_raw:
        prereq_codes = re.findall(r"0\d{6}", prerequisite_raw)
        if prereq_codes:
            prerequisite = prereq_codes

    # Semester
    semester = None
    if semester_raw and SEMESTER_RE.match(semester_raw):
        semester = semester_raw

    grade = normalize_grade(grade_raw) if grade_raw and grade_raw != "None" else None

    return {
        "course_code": course_code,
        "course_name": course_name,
        "credit_hours": credit_hours,
        "grade": grade,
        "grade_points": grade_to_points(grade),
        "grade_strength": classify_grade(grade),
        "status": status,
        "semester": semester,
        "prerequisite": prerequisite,
    }


# ── Student Metadata Extraction ───────────────────────────────

def _extract_metadata(pdf: pdfplumber.PDF) -> dict:
    """Extract student metadata from PDF text."""
    metadata = {
        "student_name": "",
        "student_id": "",
        "cumulative_gpa": None,
        "rating": "",
        "plan_hours": 0,
        "passed_hours": 0,
        "remaining_hours": 0,
        "registered_hours": 0,
        "level": "",
    }

    full_text = "\n".join(page_texts(pdf))

    id_match = re.search(r"Student Id\s*:\s*(\d+)", full_text)
    if id_match:
        metadata["student_id"] = id_match.group(1)

    name_match = re.search(r"Student Name\s*:\s*([^\n\r]+)", full_text)
    if name_match:
        metadata["student_name"] = name_match.group(1).strip()

    gpa_match = re.search(r"GPA\s*:\s*(\d+\.\d+)", full_text)
    if gpa_match:
        metadata["cumulative_gpa"] = float(gpa_match.group(1))

    rating_match = re.search(r"Grade\s*:\s*([A-Z]+)", full_text)
    if rating_match:
        metadata["rating"] = rating_match.group(1)

    plan_match = re.search(r"Plan Hrs\s*:\s*(\d+)", full_text)
    if plan_match:
        metadata["plan_hours"] = int(plan_match.group(1))

    earned_match = re.search(r"Earned Hrs\s*:\s*(\d+)", full_text)
    if earned_match:
        metadata["passed_hours"] = int(earned_match.group(1))

    remain_match = re.search(r"Remain Hrs\s*:\s*(\d+)", full_text)
    if remain_match:
        metadata["remaining_hours"] = int(remain_match.group(1))

    att_match = re.search(r"Attempted Hrs\s*:\s*(\d+)", full_text)
    if att_match:
        metadata["registered_hours"] = int(att_match.group(1))

    level_match = re.search(r"Student\s*:\s*([^\n\r]+)", full_text)
    if level_match:
        metadata["level"] = level_match.group(1).strip()

    return metadata


# ── Main Extraction Pipeline ──────────────────────────────────

def parse_academic_plan(pdf_path: str) -> dict:
    """
    Parse an English MEU academic plan PDF and return structured data.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dictionary containing student info, requirement categories, and course lists.
    """
    pdf_path = Path(pdf_path)

    categories = []
    current_category = None
    all_courses = []

    # open_pdf refuses a corrupt file and one that expands without bound, both
    # as ValueError, which every caller already maps to a 4xx. See parsing/pdf.py.
    with open_pdf(pdf_path) as pdf:
        student = _extract_metadata(pdf)

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or _is_empty_row(row):
                        continue

                    if _is_section_header(row):
                        if current_category and current_category.get("courses"):
                            categories.append(current_category)
                        info = _extract_section_info(row)
                        current_category = {
                            **info,
                            "courses": [],
                        }
                        continue

                    if _is_column_header(row):
                        continue

                    if _is_data_row(row):
                        course = _extract_course(row)
                        if current_category is not None:
                            current_category["courses"].append(course)
                        all_courses.append(course)

        if current_category and current_category.get("courses"):
            categories.append(current_category)

    # Merge category sections with identical names across pages
    merged_categories = []
    cat_map = {}
    for cat in categories:
        name = cat["category_name"]
        if name in cat_map:
            cat_map[name]["courses"].extend(cat["courses"])
        else:
            cat_map[name] = cat
            merged_categories.append(cat)

    # Compute Statistics
    passed = [c for c in all_courses if c["status"] == "passed"]
    transferred = [c for c in all_courses if c["status"] == "transferred"]
    exempted = [c for c in all_courses if c["status"] == "exempted"]
    in_progress = [c for c in all_courses if c["status"] == "in_progress"]
    not_registered = [c for c in all_courses if c["status"] == "not_registered"]

    graded_courses = [c for c in passed if c["grade_points"] is not None and c["credit_hours"] > 0]
    total_quality_points = sum(c["grade_points"] * c["credit_hours"] for c in graded_courses)
    total_graded_hours = sum(c["credit_hours"] for c in graded_courses)
    computed_gpa = round(total_quality_points / total_graded_hours, 2) if total_graded_hours > 0 else 0.0

    grade_distribution = {"strong": 0, "moderate": 0, "weak": 0, "unknown": 0}
    for c in all_courses:
        grade_distribution[c["grade_strength"]] += 1

    summary = {
        "total_courses": len(all_courses),
        "passed_courses": len(passed),
        "transferred_courses": len(transferred),
        "exempted_courses": len(exempted),
        "in_progress_courses": len(in_progress),
        "not_registered_courses": len(not_registered),
        "total_credit_hours": sum(c["credit_hours"] for c in all_courses),
        "passed_credit_hours": sum(c["credit_hours"] for c in passed),
        "computed_gpa": computed_gpa,
        "reported_gpa": student.get("cumulative_gpa"),
        "grade_distribution": grade_distribution,
    }

    return {
        "student": student,
        "categories": merged_categories,
        "all_courses": all_courses,
        "summary": summary,
    }


def save_extraction(result: dict, output_path: str) -> None:
    """Save extraction results to a JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved extraction to: {output_path}")
