"""
CareerCompass — M2: Student Skill Vector

Joins a student's confirmed transcript to the course → skill map and produces
the Student Skill Vector: what this student knows, and how well.

The whole module is deterministic arithmetic. No LLM runs here, and none may
be added: the same transcript and the same course → skill map must always
produce the same numbers, because M3 subtracts against them and a student is
shown the result. Every judgement call an LLM might make has already happened
upstream, in the extraction and matching stages.

Two numbers are reported per skill, and they answer different questions:

    proficiency   how well the student did in the material that taught this
                  skill - a weighted mean of grade attainment, 0-1
    coverage      how much of their study touched it at all - the summed
                  evidence weight, unbounded but typically 0-3

Keeping them separate matters. A student who scored A in one course that
mentions Docker once is not equivalent to one who scored B across three
courses built on it, and collapsing both into a single number hides exactly
the distinction a gap analysis needs.
"""

from careercompass.parsing.grades import grade_to_points
from careercompass.skills.matcher import ACCEPTED

MAX_GRADE_POINTS = 4.0

# An advanced treatment of a skill is stronger evidence than a passing mention
# in an introductory week. The extraction stage already assigns these levels
# from the Bloom verb of the outcome the term came from.
LEVEL_FACTOR = {
    "beginner": 0.70,
    "intermediate": 0.85,
    "advanced": 1.00,
}
DEFAULT_LEVEL_FACTOR = 0.85

# Only skills the matcher resolved confidently enter the vector. A
# needs_review row is a question, not a fact about the student, and a
# no_match row has no canonical id to join on at all. The matcher records its
# verdict under match.review_status, not on the skill itself.
ACCEPTED_STATUS = ACCEPTED

# Grades that mean the course was not completed for credit. "Equivelant" is
# the registrar's spelling for a transfer credit: the course counts toward the
# plan but carries no mark, so it contributes coverage without attainment.
NON_GRADE_STATUSES = {"registered", "exempted", "withdrawn", "incomplete"}


def _passed(course: dict) -> bool:
    """Whether a transcript row represents credit actually earned."""
    status = str(course.get("status") or "").strip().lower()
    if status in NON_GRADE_STATUSES:
        return False
    points = grade_to_points(course.get("grade"))
    return points is not None and points > 0


def _attainment(course: dict) -> float:
    """Grade as a 0-1 fraction of the maximum."""
    points = grade_to_points(course.get("grade"))
    if points is None:
        return 0.0
    return max(0.0, min(1.0, points / MAX_GRADE_POINTS))


def _evidence_weight(skill: dict) -> float:
    """How strongly one course teaches one skill."""
    weight = skill.get("weight")
    weight = 1.0 if weight is None else float(weight)
    level = LEVEL_FACTOR.get(skill.get("level"), DEFAULT_LEVEL_FACTOR)
    return max(0.0, min(1.0, weight)) * level


def _label(skill: dict, skill_id: str) -> str:
    canonical = skill.get("canonical") or {}
    match = skill.get("match") or {}
    return canonical.get("label") or match.get("canonical_label") or skill_id


def _collapse(skills: list) -> dict:
    """Reduce one course's skills to one row per canonical id.

    A syllabus mentions the same underlying skill through many terms -
    "derivatives", "integration" and "limits" all resolve to calculus - and
    summing them would let a course that phrases a topic ten ways outweigh one
    that phrases it once. The strongest single piece of evidence is what the
    course actually demonstrates, so the weights are maxed, not added.

    This is the same defect the job ontology hit on 18 August, where several
    terms resolving to one skill had their posting counts summed and put
    "monitoring and observability" at 100% of the DevOps path.
    """
    best = {}
    for skill in skills:
        match = skill.get("match") or {}
        status = match.get("review_status", skill.get("status"))
        if status != ACCEPTED_STATUS:
            continue
        canonical = skill.get("canonical") or {}
        skill_id = canonical.get("id") or match.get("canonical_id")
        if not skill_id:
            continue
        weight = _evidence_weight(skill)
        if weight <= 0:
            continue
        current = best.get(skill_id)
        if current is None or weight > current[0]:
            best[skill_id] = (weight, skill)
    return best


def build_skill_vector(
    courses: list,
    course_skills: dict,
    *,
    taxonomy_version: str = "1.0",
    career_path_id: str | None = None,
    include_unpassed: bool = False,
) -> dict:
    """
    Compute the Student Skill Vector.

    Args:
        courses: transcript rows, each with ``course_code``, ``grade`` and
            optionally ``status``, ``credit_hours`` and ``course_name``.
        course_skills: ``{course_code: [skill, ...]}``, the course → skill map.
            Each skill carries ``canonical`` (``{id, label}``), ``weight``,
            ``level`` and the matcher's ``status``.
        taxonomy_version: recorded so a vector can be invalidated when the
            taxonomy is rebuilt underneath it.
        career_path_id: recorded for M3; not used in the arithmetic.
        include_unpassed: count courses the student has not yet passed. Off by
            default - a registered-but-unfinished course is not evidence.

    Returns:
        A dict shaped for ``GET /api/v1/me/skill-profile``.
    """
    accumulator = {}
    counted = 0
    skipped = []

    for course in courses:
        code = course.get("course_code")
        if not code:
            continue
        if not include_unpassed and not _passed(course):
            skipped.append({"course_code": code, "reason": "not passed"})
            continue

        skills = course_skills.get(code)
        if skills is None:
            # Try any alternative code this course is known by, then give up.
            skills = next(
                (course_skills[alt] for alt in course.get("course_codes", [])
                 if alt in course_skills),
                None,
            )
        if not skills:
            skipped.append({"course_code": code, "reason": "no skill map"})
            continue

        counted += 1
        attainment = _attainment(course)
        grade = course.get("grade")

        for skill_id, best in _collapse(skills).items():
            weight, skill = best
            entry = accumulator.setdefault(
                skill_id,
                {
                    "skill_id": skill_id,
                    "label": _label(skill, skill_id),
                    "skill_type": skill.get("skill_type"),
                    "weighted_attainment": 0.0,
                    "coverage": 0.0,
                    "courses": [],
                },
            )
            entry["weighted_attainment"] += weight * attainment
            entry["coverage"] += weight
            entry["courses"].append(
                {
                    "course_code": code,
                    "course_name": course.get("course_name"),
                    "grade": grade,
                    "weight": round(weight, 3),
                    "level": skill.get("level"),
                }
            )

    skills_out = []
    for entry in accumulator.values():
        coverage = entry["coverage"]
        proficiency = entry["weighted_attainment"] / coverage if coverage else 0.0
        skills_out.append(
            {
                "skill_id": entry["skill_id"],
                "label": entry["label"],
                "skill_type": entry["skill_type"],
                "proficiency": round(proficiency, 4),
                "coverage": round(coverage, 4),
                "evidence": "grades",
                "course_count": len(entry["courses"]),
                "courses": sorted(entry["courses"], key=lambda c: c["course_code"]),
                "quiz_score": None,
            }
        )

    # Strongest evidence first, then best performance, then a stable tiebreak
    # so the same input always serialises identically.
    skills_out.sort(key=lambda s: (-s["coverage"], -s["proficiency"], s["skill_id"]))

    return {
        "career_path_id": career_path_id,
        "taxonomy_version": taxonomy_version,
        "source": "grades",
        "total_skills": len(skills_out),
        "courses_counted": counted,
        "courses_skipped": skipped,
        "skills": skills_out,
    }


def apply_quiz_results(vector: dict, quiz_scores: dict) -> dict:
    """
    Write quiz results over the grade-derived vector (FR-JS-22).

    A quiz measures the skill directly, so it replaces the inferred value
    rather than averaging with it; the grade-derived number is kept alongside
    so the dashboard can show what changed. A quiz for a skill the student has
    no coursework evidence for still counts - that is the point of the quiz.

    Args:
        vector: the result of ``build_skill_vector``.
        quiz_scores: ``{skill_id: score}``, each score 0-1.
    """
    if not quiz_scores:
        return vector

    by_id = {s["skill_id"]: s for s in vector["skills"]}
    touched = False

    for skill_id, score in quiz_scores.items():
        score = max(0.0, min(1.0, float(score)))
        entry = by_id.get(skill_id)
        if entry is None:
            entry = {
                "skill_id": skill_id,
                "label": skill_id,
                "skill_type": None,
                "proficiency": round(score, 4),
                "coverage": 0.0,
                "evidence": "quizzes",
                "course_count": 0,
                "courses": [],
                "quiz_score": round(score, 4),
                "proficiency_from_grades": None,
            }
            vector["skills"].append(entry)
            by_id[skill_id] = entry
        else:
            entry["proficiency_from_grades"] = entry["proficiency"]
            entry["proficiency"] = round(score, 4)
            entry["quiz_score"] = round(score, 4)
            entry["evidence"] = "grades+quizzes"
        touched = True

    if touched:
        graded = any(s["evidence"] != "quizzes" for s in vector["skills"])
        vector["source"] = "grades+quizzes" if graded else "quizzes"
        vector["total_skills"] = len(vector["skills"])
        vector["skills"].sort(
            key=lambda s: (-s["coverage"], -s["proficiency"], s["skill_id"])
        )
    return vector


def load_course_skills(paths) -> dict:
    """
    Build the course → skill map from extracted skill files.

    Keys every code a course is known by, because plan editions renumber:
    Operating Systems is 0433301 in three plans and A0413301 in the fourth,
    and a transcript quotes whichever its own plan uses.
    """
    import json
    from pathlib import Path

    mapping = {}
    for path in sorted(Path(p) for p in paths):
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        skills = record.get("skills") or []
        codes = record.get("course_codes") or [record.get("course_code")]
        for code in codes:
            if code:
                mapping[code] = skills
    return mapping
