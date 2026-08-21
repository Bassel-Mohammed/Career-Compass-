"""
CareerCompass — M3: Skill Gap

Subtracts the Student Skill Vector (M2) from a career path's required skills
and classifies each requirement. Like M2 this is deterministic arithmetic: the
same vector and the same ontology must always produce the same gap, because a
student is shown the result and acts on it.

Exactly one field is LLM-generated — ``narrative`` — and it explains numbers
the system already computed. It never produces a score. That boundary is the
point: a gap a model could nudge is a gap nobody can audit.

Three classifications, not two. FR-JS-13 asks for two categories while the
dashboard and interface assume three; the review resolved this in favour of
three, so a requirement is `strong`, `moderate` or `weak`.

A note on the word *coverage*, which means two unrelated things either side of
this join and must not be confused:

    vector coverage   how much of the student's study touched a skill
    ontology coverage how many postings ask for it

The second is surfaced here as ``importance``, and the first is never exposed
as "coverage" in a gap row.
"""

import json
from pathlib import Path

# What proficiency each required_level asks for, on the vector's 0-1 scale.
#
# The target comes from required_level, NOT from required_score. Those are
# different quantities and confusing them is the easiest mistake to make here:
#
#     required_level   how deeply the market wants the skill  (the target)
#     required_score   what share of postings mention it      (the importance)
#
# required_score has a median of about 5 across a path, so comparing a
# student's attainment against it classifies nearly every requirement as
# already met. API_DESIGN.md sketches required_level as a bare number; the
# ontology produces a category plus a frequency, and this follows the data.
LEVEL_TARGET = {
    "beginner": 0.50,
    "intermediate": 0.70,
    "advanced": 0.85,
}
DEFAULT_TARGET = 0.70

# A requirement the student meets or exceeds is strong; one they hold but
# below the level asked for is moderate; anything further down is weak. The
# boundaries are a fraction of the target rather than an absolute proficiency,
# so being slightly short of an advanced requirement is not reported the same
# way as never having studied it.
STRONG_RATIO = 1.0
MODERATE_RATIO = 0.7

# How much evidence a requirement needs before "strong" is claimable, on the
# vector's `coverage` scale (summed evidence weight, typically 0-3).
#
# Without this, proficiency alone decides — and for a student with one course,
# proficiency *is* their grade. The attainment term is constant across that
# course's skills, so it cancels out of the weighted mean entirely: an A gives
# 1.0 for every skill the syllabus names, whether it built a module on it or
# mentioned it once in a week heading. Measured, that reported
# `monitoring and observability` as strong from the single word "Monitors", and
# every strong row in a two-course profile read exactly 1.000.
#
# The numbers come from the measured distribution over all 20 extracted courses
# (138 skills, p25 0.56, p50 0.70, p75 1.02). A single beginner mention floors
# at 0.42 (weight 0.6 x level factor 0.70), so an advanced requirement now needs
# top-quartile evidence rather than one passing mention.
#
# Like the matcher thresholds, these are starting points, not settled values.
LEVEL_COVERAGE = {
    "beginner": 0.50,
    "intermediate": 0.70,
    "advanced": 1.00,
}
DEFAULT_COVERAGE = 0.70

STRONG, MODERATE, WEAK = "strong", "moderate", "weak"

# Soft skills top nearly every career path, which is an accurate reading of job
# postings and useless as advice: ranked first, they give every student the
# same three recommendations regardless of what they studied. Technical
# requirements are ranked first by default and soft ones reported alongside.
SOFT_TYPE = "soft"


def _classify(current: float, required: float, coverage: float = None,
              required_coverage: float = 0.0) -> str:
    """Classify one requirement from both halves of the vector.

    `current` is proficiency — how well they did. `coverage` is how much of
    their study touched the skill. M3 needs both: passing the proficiency bar on
    a single passing mention is not the same as passing it across a course built
    on the subject, and reporting them identically is what made every "strong"
    row untrustworthy.

    `coverage` of None means the student does not hold the skill at all, which
    the proficiency test already resolves to weak.
    """
    if required <= 0:
        return STRONG
    ratio = current / required
    if ratio >= STRONG_RATIO:
        # Met on performance; now, is there enough evidence behind it?
        if coverage is not None and coverage < required_coverage:
            return MODERATE
        return STRONG
    if ratio >= MODERATE_RATIO:
        return MODERATE
    return WEAK


def build_skill_gap(
    vector: dict,
    requirements: list,
    *,
    career_path: str = None,
    include_soft: bool = True,
) -> dict:
    """
    Compare a skill vector against one career path's requirements.

    Args:
        vector: the result of ``skills.vector.build_skill_vector``.
        requirements: ontology rows for one career path, each carrying
            ``skill_id``, ``skill_label``, ``required_level``, ``coverage``
            and optionally ``skill_type``.
        career_path: recorded on the result; defaults to the rows' own path.
        include_soft: report soft-skill requirements. They are always ranked
            after technical ones; this drops them entirely.

    Returns:
        A dict shaped for ``GET /api/v1/me/skill-gap``.
    """
    held = {s["skill_id"]: s for s in vector.get("skills", [])}

    rows = []
    for req in requirements:
        skill_id = req.get("skill_id")
        if not skill_id:
            continue
        skill_type = req.get("skill_type")
        is_soft = skill_type == SOFT_TYPE
        if is_soft and not include_soft:
            continue

        required = LEVEL_TARGET.get(req.get("required_level"), DEFAULT_TARGET)
        required_coverage = LEVEL_COVERAGE.get(
            req.get("required_level"), DEFAULT_COVERAGE)
        entry = held.get(skill_id)
        current = float(entry["proficiency"]) if entry else 0.0
        coverage = float(entry.get("coverage") or 0.0) if entry else None

        rows.append({
            "skill_id": skill_id,
            "label": req.get("skill_label") or (entry or {}).get("label") or skill_id,
            "skill_type": skill_type,
            "required_level": req.get("required_level"),
            "required_proficiency": round(required, 4),
            "current_level": round(current, 4),
            # The other half of the vector, surfaced so a consumer can see how
            # much study is behind `current_level`. Named `evidence_coverage`
            # and not `coverage` on purpose: this row already carries
            # `importance`, which is the *ontology's* coverage. The two mean
            # unrelated things and the module docstring exists to keep them apart.
            "evidence_coverage": round(coverage, 4) if coverage is not None else 0.0,
            "required_coverage": round(required_coverage, 4),
            # Only ever a shortfall. A student exceeding a requirement has no
            # gap to close, and a negative number here would sort above real
            # gaps and be subtracted again downstream.
            "gap": round(max(0.0, required - current), 4),
            "classification": _classify(current, required, coverage, required_coverage),
            # How often the market asks for it, so a dashboard can sort by
            # what employers actually want rather than alphabetically.
            "importance": round(float(req.get("coverage") or 0.0), 4),
            # What closing this gap is worth. Ranking on the gap alone puts
            # every unstudied skill at the top in arbitrary order - Power BI,
            # asked for by 2% of Cybersecurity postings, above Linux at 18% -
            # because both score a full-width gap. Weighting by demand is the
            # difference between a list of everything the student has not done
            # and a list of what to do next.
            "priority": round(max(0.0, required - current)
                              * float(req.get("coverage") or 0.0), 4),
            "evidence": (entry or {}).get("evidence"),
            "course_count": (entry or {}).get("course_count", 0),
            "courses": (entry or {}).get("courses", []),
        })

    # Technical before soft, then by what closing the gap is worth, then by
    # raw gap, then by id so the same input always serialises identically.
    rows.sort(key=lambda r: (
        r["skill_type"] == SOFT_TYPE,
        -r["priority"],
        -r["gap"],
        r["skill_id"],
    ))

    summary = {STRONG: 0, MODERATE: 0, WEAK: 0}
    for row in rows:
        summary[row["classification"]] += 1

    path = career_path or next(
        (r.get("career_path") for r in requirements if r.get("career_path")), None)

    return {
        "career_path": path,
        "taxonomy_version": vector.get("taxonomy_version"),
        "source": vector.get("source"),
        "summary": summary,
        "total_requirements": len(rows),
        "requirements_met": summary[STRONG],
        "skills": rows,
        "narrative": None,
    }


def top_gaps(gap: dict, limit: int = 10, *, technical_only: bool = True) -> list:
    """The requirements worth acting on first, ranked by ``priority``."""
    rows = [r for r in gap["skills"] if r["classification"] != STRONG]
    if technical_only:
        rows = [r for r in rows if r["skill_type"] != SOFT_TYPE]
    return rows[:limit]


NARRATIVE_PROMPT = """You are advising a computing student on their skill gap \
for a career as {path}.

Here is what the analysis already computed. Every number is final.

Strong (meets or exceeds what the market asks): {strong}
Partly there: {moderate}
Missing or far below: {weak}

The gaps worth closing first, with how much of the market asks for each:
{gaps}

{strengths_line}

Write 3-5 sentences of plain advice for the student. Name the specific skills \
above. Say what they are already good at, then what to work on first and why \
it matters for this career path.

Do not invent skills that are not listed. Do not give numeric scores, \
percentages or ratings of any kind. Do not use headings or bullet points."""


def _narrative_inputs(gap: dict, limit: int = 5) -> dict:
    rows = top_gaps(gap, limit)
    gaps = "\n".join(
        f"- {r['label']} (asked for by {round(r['importance'] * 100)}% of postings)"
        for r in rows
    ) or "- none: every technical requirement is met"

    strong = [r["label"] for r in gap["skills"]
              if r["classification"] == STRONG and r["skill_type"] != SOFT_TYPE][:5]
    strengths = (f"Already strong: {', '.join(strong)}." if strong
                 else "Nothing yet reaches the level this path asks for.")

    return {
        "path": gap.get("career_path") or "this field",
        "strong": gap["summary"][STRONG],
        "moderate": gap["summary"][MODERATE],
        "weak": gap["summary"][WEAK],
        "gaps": gaps,
        "strengths_line": strengths,
    }


def write_narrative(gap: dict, decider=None, limit: int = 5) -> dict:
    """
    Attach a plain-language explanation of a gap that is already computed.

    This is the only generated field in M3, and it is given the numbers rather
    than the data: the model sees labels, counts and a market percentage, and
    is asked for prose. It cannot alter a classification, a gap or a priority,
    because it never sees the vector and nothing it returns is parsed back into
    a number.

    Failure is not an error. A gap without a narrative is still a complete,
    usable gap, so an unavailable or misbehaving model leaves ``narrative``
    None rather than failing the request.

    Args:
        gap: the result of ``build_skill_gap``. Modified in place.
        decider: an object exposing ``.available`` and ``.complete(prompt)``.
            Defaults to the configured LLM.
        limit: how many gaps to mention.
    """
    if decider is None:
        from careercompass.skills.llm import LLMDecider
        decider = LLMDecider()

    if not getattr(decider, "available", False):
        gap["narrative"] = None
        return gap

    prompt = NARRATIVE_PROMPT.format(**_narrative_inputs(gap, limit))
    try:
        text = decider.complete(prompt)
    except Exception:  # noqa: BLE001 - prose is optional, the numbers are not
        text = None

    text = (text or "").strip()
    gap["narrative"] = text or None
    return gap


def load_requirements(path, career_path: str = None) -> list:
    """
    Load ontology rows from the artifact `save_ontology` writes.

    Args:
        path: path to `career_path_skills.json`.
        career_path: return only this path's rows; all paths if omitted.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("skills", data) if isinstance(data, dict) else data
    if career_path:
        rows = [r for r in rows if r.get("career_path") == career_path]
    return rows


def attach_skill_types(requirements: list, taxonomy_path) -> list:
    """
    Fill in `skill_type` from the taxonomy for rows that lack it.

    Ontology rows built before `skill_type` was threaded through carry None,
    and the whole point of the column is that soft requirements can be ranked
    apart. Rows are updated in place and returned.
    """
    types = {}
    with Path(taxonomy_path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                record = json.loads(line)
                types[record["id"]] = record.get("skill_type")

    for row in requirements:
        if not row.get("skill_type"):
            row["skill_type"] = types.get(row.get("skill_id"))
    return requirements
