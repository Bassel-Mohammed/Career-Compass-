"""
CareerCompass — Grade & Status Utilities

Provides:
    - Letter grade → GPA point conversion (MEU 4.0 scale)
    - Grade strength classification (strong / moderate / weak)
    - Standardized grade normalization
"""

# ── Grade → GPA Points (MEU 4.0 scale) ────────────────────────

GRADE_POINTS = {
    "A":  4.00,
    "-A": 3.67,
    "A-": 3.67,
    "+B": 3.33,
    "B+": 3.33,
    "B":  3.00,
    "-B": 2.67,
    "B-": 2.67,
    "+C": 2.33,
    "C+": 2.33,
    "C":  2.00,
    "-C": 1.67,
    "C-": 1.67,
    "+D": 1.33,
    "D+": 1.33,
    "D":  1.00,
    "-D": 0.67,
    "D-": 0.67,
    "F":  0.00,
}


def normalize_grade(raw_grade: str | None) -> str | None:
    """
    Normalize grade strings extracted from PDF.
    Normalizes prefix modifiers like "-A" -> "A-", "+B" -> "B+".
    """
    if not raw_grade or not raw_grade.strip():
        return None

    g = raw_grade.strip()

    if len(g) == 2 and g[0] in "+-" and g[1].isalpha():
        return g[1] + g[0]

    if g in GRADE_POINTS:
        return g

    return g


def grade_to_points(grade: str | None) -> float | None:
    """Convert a letter grade to its GPA point value."""
    if grade is None:
        return None
    normalized = normalize_grade(grade)
    if normalized is None:
        return None
    return GRADE_POINTS.get(normalized)


def classify_grade(grade: str | None) -> str:
    """
    Classify a grade into strength categories for skill gap analysis.

    Returns:
        "strong"   — A, A-, B+, B  (≥ 3.0)
        "moderate" — B-, C+, C     (≥ 2.0)
        "weak"     — C-, D+, D, F  (< 2.0)
        "unknown"  — no grade / unrecognized
    """
    pts = grade_to_points(grade)
    if pts is None:
        return "unknown"
    if pts >= 3.0:
        return "strong"
    if pts >= 2.0:
        return "moderate"
    return "weak"
