"""
CareerCompass — Course Syllabus PDF Parser

Extracts the skill-bearing content of MEU course syllabus PDFs
(form F112-3-1, Rev. d) using pdfplumber.

Returns only the fields skill extraction and the course graph need:

    - Course identity (code, title, credit/theoretical/practical hours, JNQF level)
    - Prerequisite course codes
    - Course description
    - Course Learning Outcomes with their JNQF descriptor tier and Bloom verb
    - Weekly topics and lab sessions with CLO coverage
    - Structural warnings for inconsistent source documents

"""

import re
import json
import pdfplumber
from pathlib import Path

# ── Regex Patterns ─────────────────────────────────────────────
COURSE_CODE_RE = re.compile(r"\b0\d{6}\b")
WEEK_RE = re.compile(r"^\d{1,2}$")
LECTURE_NO_RE = re.compile(r"^Lecture\s*\(\s*\d+\s*\)$", re.IGNORECASE)
LAB_RE = re.compile(r"^Lab\s*\d*\s*[:.\-]", re.IGNORECASE | re.MULTILINE)
WEIGHT_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*%?\s*$")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
LEADING_INDEX_RE = re.compile(r"^\d+\s*[.)]?\s*")

# Wingdings/Symbol private-use glyphs the MEU template uses for
# checkboxes and bullets. They carry no recoverable state in the text
# layer, so they are stripped rather than interpreted.
CHECKBOX_GLYPHS = ""

# ── Section Titles ─────────────────────────────────────────────
SECTION_DETAILS = "Course Details"
SECTION_DESCRIPTION = "Course Description"

# Labels are matched by prefix so template wording drift
# ("Course Level (according to JNQF )" vs "...JNQF)") still resolves.
DETAIL_LABELS = {
    "Course Title": "course_title",
    "Course No.": "course_code",
    "Credit Hours": "credit_hours",
    "Theoretical": "theoretical_hours",
    "Practical": "practical_hours",
    "Course Level": "jnqf_level",
    "Pre-requisite": "prerequisites_raw",
    "Co-requisite": "corequisites_raw",
}

JNQF_TIERS = ("knowledge", "skill", "competency")


# ── Cell Helpers ───────────────────────────────────────────────
def _clean(cell) -> str:
    """Normalize a cell, preserving line breaks (topic cells are multi-line)."""
    if cell is None:
        return ""
    text = str(cell)
    for glyph in CHECKBOX_GLYPHS:
        text = text.replace(glyph, " ")
    text = text.replace("\u200F", "").replace("\u200E", "")
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _flat(cell) -> str:
    """Normalize a cell down to a single line."""
    return re.sub(r"\s+", " ", _clean(cell)).strip()


def _lines(cell) -> list:
    """Split a multi-line cell into non-empty stripped lines."""
    return [line for line in _clean(cell).split("\n") if line]


def _split_topics_and_labs(cell) -> tuple:
    """
    Split a schedule topic cell into lecture topics and lab sessions.

    Lab titles wrap onto continuation lines ("Lab3: Getting Started with
    ROS 2 on" / "Linux"), so the cell is cut at each lab marker and each
    lab chunk is rejoined instead of being split line by line.
    """
    text = _clean(cell)
    if not text:
        return [], []

    markers = list(LAB_RE.finditer(text))
    if not markers:
        return _lines(text), []

    topics = [line for line in text[:markers[0].start()].split("\n") if line]
    labs = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        labs.append(re.sub(r"\s+", " ", text[marker.start():end]).strip())
    return topics, labs


def _to_int(text: str):
    """Parse the first integer in a string, or None."""
    match = NUMBER_RE.search(text or "")
    return int(float(match.group(0))) if match else None


def _to_float(text: str):
    """Parse the first number in a string, or None."""
    match = NUMBER_RE.search(text or "")
    return float(match.group(0)) if match else None


def _parse_id_list(text: str) -> list:
    """Extract a list of integer ids from cells like '1,2', 'PLO 1' or '-'."""
    return [int(n) for n in re.findall(r"\d+", text or "")]


def _match_label(text: str, labels: dict):
    """Return the output key for a cell that is a known section label."""
    for label, key in labels.items():
        if text.startswith(label):
            return key
    return None


def _key_values(rows: list, labels: dict) -> dict:
    """
    Pair labels with their values within each row.

    The template scatters label/value pairs across a variable number of
    columns and pads with empty cells, so cells are flattened per row and
    each recognized label takes the next cell that is not itself a label.
    """
    found = {}
    for row in rows:
        cells = [c for c in (_flat(cell) for cell in row) if c]
        for index, cell in enumerate(cells):
            key = _match_label(cell, labels)
            if not key or key in found:
                continue
            if index + 1 < len(cells):
                value = cells[index + 1]
                if _match_label(value, labels) is None:
                    found[key] = value
    return found


# ── Row Classification ─────────────────────────────────────────
def _is_section(table: list, title: str) -> bool:
    """Check whether a table is the section introduced by the given title."""
    if not table:
        return False
    for row in table[:2]:
        for cell in row:
            if _flat(cell).startswith(title):
                return True
    return False


def _is_clo_table(table: list) -> bool:
    """
    Check whether a table is the Course Learning Outcomes table.

    Keyed on the "JNQF Descriptors" header rather than "CLOs": the weekly
    schedule also has a column headed "CLOs" and would otherwise match.
    """
    if not table:
        return False
    for row in table[:2]:
        if any(_flat(cell).startswith("JNQF Descriptors") for cell in row):
            return True
    return False


def _is_session_row(row: list) -> bool:
    """
    Check whether a row is a weekly-schedule lecture row.

    Rows are classified by shape rather than by their parent table: the
    schedule fragments into several table objects per page, and the
    continuation fragments carry no header.
    """
    if len(row) < 5:
        return False
    week = _flat(row[0])
    lecture_no = _flat(row[2])
    if LECTURE_NO_RE.match(lecture_no):
        return True
    return bool(WEEK_RE.match(week) and _flat(row[1]))


def _is_assessment_row(row: list) -> bool:
    """Check whether a row is an evaluation-weight row."""
    if len(row) != 3:
        return False
    return bool(_flat(row[0])) and bool(WEIGHT_RE.match(_flat(row[1])))


# ── Section Extraction ─────────────────────────────────────────
def _extract_course(rows: list) -> dict:
    """Extract course identity from the Course Details rows."""
    raw = _key_values(rows, DETAIL_LABELS)

    return {
        "course_code": raw.get("course_code", ""),
        "course_title": raw.get("course_title", ""),
        "credit_hours": _to_int(raw.get("credit_hours", "")),
        "theoretical_hours": _to_int(raw.get("theoretical_hours", "")),
        "practical_hours": _to_int(raw.get("practical_hours", "")),
        "jnqf_level": _to_int(raw.get("jnqf_level", "")),
        "prerequisites": COURSE_CODE_RE.findall(raw.get("prerequisites_raw", "")),
    }


def _extract_description(table: list) -> str:
    """Extract the course description paragraph."""
    for row in table[1:]:
        for cell in row:
            text = _flat(cell)
            if text and not text.startswith(SECTION_DESCRIPTION):
                return text
    return ""


def _extract_clos(table: list) -> list:
    """
    Extract Course Learning Outcomes.

    The JNQF Descriptors columns are marked either with a check glyph or
    with a descriptor code such as "K1-P" / "S1-D", so a column counts as
    marked when its cell is non-empty. The leading Bloom verb is kept
    because it grades the depth of the outcome alongside the tier.
    """
    clos = []

    for row in table:
        if len(row) < 3:
            continue
        number = _flat(row[0])
        text = _flat(row[1])
        if not WEEK_RE.match(number) or not text:
            continue

        markers = {
            tier: _flat(row[3 + offset]) if 3 + offset < len(row) else ""
            for offset, tier in enumerate(JNQF_TIERS)
        }
        words = text.split()

        clos.append({
            "number": int(number),
            "text": text,
            "jnqf_descriptor": next((t for t in JNQF_TIERS if markers[t]), None),
            "bloom_verb": words[0] if words else "",
        })

    return clos


def _extract_sessions(tables: list) -> list:
    """
    Extract weekly-schedule rows in document order.

    A week number appears only on the first lecture row of each week, so it
    is carried forward; rows that inherit it are flagged so the validator
    can tell a stated week from an inferred one.
    """
    sessions = []
    current_week = None

    for table in tables:
        for row in table:
            if not _is_session_row(row):
                continue

            week_cell = _flat(row[0])
            stated = bool(WEEK_RE.match(week_cell))
            if stated:
                current_week = int(week_cell)
            if current_week is None:
                continue

            topics, labs = _split_topics_and_labs(row[1] if len(row) > 1 else "")
            sessions.append({
                "week": current_week,
                "week_stated": stated,
                "topics": topics,
                "labs": labs,
                "clos": _parse_id_list(_flat(row[4]) if len(row) > 4 else ""),
            })

    return sessions


def _group_weeks(sessions: list) -> list:
    """Group lecture rows into weeks, merging topics, labs and CLO coverage."""
    weeks = []
    index = {}

    for session in sessions:
        number = session["week"]
        if number not in index:
            index[number] = {"week": number, "topics": [], "labs": [], "clos": []}
            weeks.append(index[number])
        week = index[number]

        for field in ("topics", "labs", "clos"):
            for value in session[field]:
                if value not in week[field]:
                    week[field].append(value)

    for week in weeks:
        week["clos"].sort()
    return weeks


def _extract_assessments(tables: list) -> list:
    """
    Extract evaluation weights.

    Not returned by the parser: the weights are read only so the validator
    can confirm they add up to 100% and flag the syllabus if they do not.
    """
    assessments = []
    for table in tables:
        for row in table:
            if not _is_assessment_row(row):
                continue
            assessments.append({
                "tool": LEADING_INDEX_RE.sub("", _flat(row[0])).strip().rstrip("."),
                "weight": _to_float(_flat(row[1])),
            })
    return assessments


# ── Validation ─────────────────────────────────────────────────
def _collect_warnings(course: dict, clos: list, weeks: list, sessions: list,
                      assessments: list, description: str) -> list:
    """Flag structural inconsistencies rather than silently normalizing them."""
    warnings = []

    if not course["course_code"]:
        warnings.append("Course code not found in Course Details")
    if not course["course_title"]:
        warnings.append("Course title not found in Course Details")
    if not description:
        warnings.append("Course description is empty")
    if not clos:
        warnings.append("No course learning outcomes extracted")
    if not weeks:
        warnings.append("No weekly schedule rows extracted")

    untiered = [c["number"] for c in clos if not c["jnqf_descriptor"]]
    if untiered:
        warnings.append(f"CLOs without a JNQF descriptor: {untiered}")

    defined = {c["number"] for c in clos}
    referenced = {clo for week in weeks for clo in week["clos"]}
    unknown = sorted(referenced - defined)
    if unknown:
        warnings.append(f"Weekly schedule references undefined CLOs: {unknown}")

    uncovered = sorted(defined - referenced)
    if uncovered:
        warnings.append(f"CLOs never covered by the weekly schedule: {uncovered}")

    stated = [s["week"] for s in sessions if s["week_stated"]]
    for previous, following in zip(stated, stated[1:]):
        if following - previous > 1:
            warnings.append(
                f"Week numbering jumps {previous} -> {following}; rows for the "
                f"missing week(s) carry no number and were merged into week {previous}"
            )

    total = sum(a["weight"] or 0 for a in assessments)
    if assessments and abs(total - 100) > 0.01:
        warnings.append(f"Assessment weights total {total:g}%, expected 100%")

    return warnings


# ── Main Extraction Pipeline ──────────────────────────────────
def parse_syllabus(pdf_path: str) -> dict:
    """
    Parse an MEU course syllabus PDF and return its skill-bearing content.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dictionary with the keys:
            source_file        original PDF filename
            course_code        e.g. "0432405", the join key to the transcript
            course_title       e.g. "Robotics Programming"
            credit_hours       total credit hours
            theoretical_hours  lecture hours
            practical_hours    lab hours; 0 means the course is theory only
            jnqf_level         national qualifications framework level
            prerequisites      list of prerequisite course codes
            description        the course description paragraph
            clos               list of {number, text, jnqf_descriptor, bloom_verb}
            weeks              list of {week, topics, labs, clos}
            warnings           structural problems found in the source PDF

    Raises:
        FileNotFoundError: If the PDF does not exist.
        ValueError: If the PDF has no extractable text layer.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    tables = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        text_length = sum(len(page.extract_text() or "") for page in pdf.pages)
        if text_length < 200:
            raise ValueError(
                f"No text layer found in {pdf_path.name}; the file is likely "
                "a scan and needs OCR before it can be parsed."
            )
        for page in pdf.pages:
            tables.extend(page.extract_tables())

    course = {}
    description = ""
    clos = []

    # Named sections are consumed here; whatever is left over is scanned for
    # schedule rows, because the weekly table fragments into several
    # headerless table objects that cannot be identified on their own.
    remaining = []
    for table in tables:
        if _is_section(table, SECTION_DETAILS):
            course = _extract_course(table)
        elif _is_section(table, SECTION_DESCRIPTION):
            description = _extract_description(table)
        elif _is_clo_table(table):
            clos = _extract_clos(table)
        else:
            remaining.append(table)

    if not course:
        course = _extract_course([])

    sessions = _extract_sessions(remaining)
    weeks = _group_weeks(sessions)
    assessments = _extract_assessments(tables)

    return {
        "source_file": pdf_path.name,
        **course,
        "description": description,
        "clos": clos,
        "weeks": weeks,
        "warnings": _collect_warnings(
            course, clos, weeks, sessions, assessments, description
        ),
    }


def save_syllabus(result: dict, output_path: str) -> None:
    """Save parsed syllabus data to a JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved syllabus to: {output_path}")

print(parse_syllabus("/home/almadhoun/Desktop/career_compass/Robotics Syl.pdf"))