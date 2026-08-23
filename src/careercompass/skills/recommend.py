"""
CareerCompass — M4: Course Recommendation

Turns a skill gap into a ranked list of real courses that close it.

Nothing here generates a course. Items are retrieved from the catalog index
built by ``skills.course_index`` and re-ranked, exactly as `API_DESIGN.md`
requires — *"never generated freely, so the system cannot invent a course that
does not exist. Every item carries a real url."* That constraint is the reason
M4 waited for real catalog data rather than being filled with synthetic rows
the way the missing syllabi were: a wrong skill match is invisible, but a
recommended course whose link is dead is something the student clicks.

The `explanation` is written from the **student's gap**, never from the course
description. That is not only a licensing matter — the platforms' catalog text
is not ours to republish — it is also better advice: "the container work your
coursework never covered, asked for by 18% of Cybersecurity postings" tells the
student something the course's own marketing copy cannot.
"""

import logging

from careercompass.skills.gap import SOFT_TYPE, STRONG

logger = logging.getLogger(__name__)

# How well a course's level suits a gap. A student who has never touched a
# skill needs the introduction, not the masterclass; one who is most of the
# way there is wasting time on the introduction. Courses whose level could not
# be inferred score in the middle rather than last — unknown is not bad.
LEVEL_FIT = {
    "weak": {"beginner": 1.0, None: 0.6, "intermediate": 0.5, "advanced": 0.2},
    "moderate": {"intermediate": 1.0, None: 0.7, "advanced": 0.7, "beginner": 0.4},
    "strong": {"advanced": 1.0, None: 0.6, "intermediate": 0.5, "beginner": 0.2},
}
DEFAULT_FIT = 0.5

# Recommending a course a student cannot follow is not a recommendation. The
# catalog is multilingual; the curriculum here is taught in English.
DEFAULT_LANGUAGE = "en"
LANGUAGE_PENALTY = 0.25

MAX_PER_SKILL = 3


def _level_fit(classification: str, level: str) -> float:
    return LEVEL_FIT.get(classification, {}).get(level, DEFAULT_FIT)


def _relevance(course: dict, gap_row: dict, language: str) -> float:
    """How well this course answers this need, on a real 0-1 scale.

    Deliberately bounded rather than clipped. An earlier version multiplied a
    title-match bonus into the score, which pushed most results past 1.0 and
    clipped them all to exactly 1.000 — every recommendation looked equally
    relevant, which is the same as having no ranking at all.

    Three things make a course the right answer, and nothing else belongs here:
    it is *about* the skill, it is pitched at a level the student can use, and
    the market wants it. Which *skill* to address first is a separate question,
    answered by the gap's own priority in ``_sort_key``.
    """
    title = 1.0 if course.get("in_title") else 0.0
    fit = _level_fit(gap_row.get("classification"), course.get("level"))
    importance = min(1.0, float(gap_row.get("importance") or 0.0))

    score = 0.45 * title + 0.30 * fit + 0.25 * importance

    if language and course.get("language") and course["language"] != language:
        score *= LANGUAGE_PENALTY

    # Only some platforms publish a rating; Coursera's public API does not.
    # It nudges rather than dominates, so its absence cannot flatten a ranking.
    rating = course.get("rating")
    if rating:
        score *= 0.9 + 0.1 * (float(rating) / 5.0)

    return max(0.0, min(1.0, score))


def _sort_key(relevance: float, gap_row: dict) -> float:
    """What to show first: the best course for the most valuable gap.

    `priority` already carries the shortfall weighted by market demand, so this
    inherits that ordering rather than re-deriving it, while relevance keeps
    its own meaning in the response.
    """
    return relevance * (0.25 + float(gap_row.get("priority") or 0.0))


def _explain(gap_row: dict, course: dict) -> str:
    """One line, written from the gap. Never from the course description."""
    label = gap_row.get("label") or gap_row.get("skill_id")
    demand = round(float(gap_row.get("importance") or 0.0) * 100)
    level = course.get("level")

    if gap_row.get("classification") == "weak":
        opening = f"Your coursework shows no evidence of {label}"
    else:
        opening = f"You have some {label}, but below what the role asks for"

    demand_clause = (f", and {demand}% of postings on this path ask for it"
                     if demand else "")
    level_clause = f" This is a {level}-level course." if level else ""
    return f"{opening}{demand_clause}.{level_clause}"


def recommend_courses(gap: dict, index: dict, *, limit: int = 10,
                      platform: str = None, skill_id: str = None,
                      language: str = DEFAULT_LANGUAGE,
                      per_skill: int = MAX_PER_SKILL,
                      include_soft: bool = False) -> dict:
    """
    Recommend courses for the unmet requirements in a skill gap.

    Args:
        gap: the result of ``skills.gap.build_skill_gap``.
        index: ``{skill_id: [course records]}`` from ``skills.course_index``.
        limit: total items to return.
        platform: restrict to one platform (`coursera`, `ocw`, `youtube`).
        skill_id: recommend for one skill only.
        language: preferred course language; others are penalised, not dropped,
            so a student still sees something when nothing English exists.
        per_skill: cap per skill, so one well-covered gap cannot fill the list.
        include_soft: recommend for soft skills too. Off by default — they top
            every career path and would crowd out the technical advice.

    Returns:
        A dict shaped for ``GET /api/v1/me/recommendations``.
    """
    rows = [row for row in gap.get("skills", [])
            if row.get("classification") != STRONG]
    if skill_id:
        rows = [row for row in rows if row.get("skill_id") == skill_id]
    if not include_soft:
        rows = [row for row in rows if row.get("skill_type") != SOFT_TYPE]

    items, skills_without_courses = [], []

    for row in rows:
        courses = index.get(row.get("skill_id")) or []
        if platform:
            courses = [c for c in courses if c.get("platform") == platform]
        if not courses:
            # Carry the label. This list is the answer to "why is there nothing
            # here for X", and as bare ESCO UUIDs it could not be shown to
            # anyone or resolved by a caller that has no taxonomy.
            skills_without_courses.append({
                "skill_id": row.get("skill_id"),
                "skill_label": row.get("label") or row.get("skill_id"),
            })
            continue

        scored = sorted(
            ((_relevance(course, row, language), course) for course in courses),
            # Course id breaks ties so the same inputs always serialise the same.
            key=lambda pair: (-pair[0], pair[1]["course_id"]),
        )
        for relevance, course in scored[:per_skill]:
            items.append({
                "skill_id": row.get("skill_id"),
                "skill_label": row.get("label"),
                "course": {
                    "course_id": course["course_id"],
                    "title": course["title"],
                    "platform": course["platform"],
                    "url": course["url"],
                    "level": course.get("level"),
                    "language": course.get("language"),
                    "duration_hours": course.get("duration_hours"),
                    "rating": course.get("rating"),
                },
                "matched_in_title": bool(course.get("in_title")),
                "relevance": round(relevance, 4),
                "explanation": _explain(row, course),
                "_rank": _sort_key(relevance, row),
            })

    items.sort(key=lambda item: (-item["_rank"], item["course"]["course_id"]))
    for item in items:
        del item["_rank"]
    items = items[:limit]

    return {
        "career_path": gap.get("career_path"),
        "total": len(items),
        "items": items,
        # Surfaced rather than hidden: it is the honest answer to "why is there
        # nothing here for X", and it is the list of gaps the catalog cannot
        # currently serve, which is what tells you to widen it.
        "skills_without_courses": sorted(
            {row["skill_id"]: row for row in skills_without_courses}.values(),
            key=lambda row: row["skill_id"],
        ),
    }
