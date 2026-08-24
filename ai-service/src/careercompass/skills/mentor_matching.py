"""
CareerCompass — Mentor Matching (M6)

Ranks a supplied list of mentors against one student's skill gap.

The central decision here is *what* a mentor is matched against. Matching them to the
student's strengths would rank highest the mentor who can teach them least — so the score is
built from the gaps a mentor could help close, weighted by how much closing each gap is
worth. `priority` already carries that weighting: it is the shortfall scaled by how often the
job market asks for the skill.

Mentors are supplied by the caller and never invented. This service holds no mentor records,
and every returned id must have arrived in the request.

## The evidence problem, stated plainly

A mentor's expertise is the input this ranking needs and the one the platform does not yet
collect. An expert record currently carries a name, a study field, a starting year and a
status — nothing about what they actually know. So each mentor is scored from the best
evidence available, and the response says which was used:

* ``stated`` — the caller supplied ``expertise_terms``, resolved against the taxonomy through
  the same matcher the syllabus pipeline uses. This is the signal worth having.
* ``inferred`` — no terms, so the study field is mapped to career paths and their required
  skills stand in. Broad and generous, and discounted accordingly.
* ``none`` — the study field is not in the reviewed mapping. No skills are attributed, and
  the mentor ranks on seniority alone.

A caller must not present an ``inferred`` match as though the mentor had claimed the skill.
The honest fix is to collect expertise terms; this module is designed so that doing so
improves the ranking without any contract change.
"""

import json
import logging
import re
from datetime import date
from functools import lru_cache

from careercompass.config import STUDY_FIELD_CAREER_PATHS_PATH
from careercompass.skills.gap import load_requirements
from careercompass.skills.matcher import ACCEPTED
from careercompass.skills.ontology import ONTOLOGY_PATH

logger = logging.getLogger("careercompass.mentor_matching")

#: Only gaps the student has not already closed are worth a mentor's time.
UNMET_CLASSIFICATIONS = ("weak", "moderate")

#: How the two halves of the score are balanced. Coverage dominates: a very senior mentor who
#: works on none of the student's gaps is still the wrong introduction.
COVERAGE_WEIGHT = 0.75
SENIORITY_WEIGHT = 0.25

#: Years of experience treated as full marks. Beyond this, more years do not keep raising the
#: score — the difference between 12 and 20 years is not what decides whether a mentor helps.
SENIORITY_FULL_YEARS = 10

#: Applied to coverage derived from a study field rather than stated expertise.
INFERRED_CONFIDENCE = 0.6

#: How many of the student's gaps a mentor is scored against, highest priority first.
#:
#: Scoring against *every* gap sounds fairer and is not. A student on Backend Development has
#: around a hundred open requirements, so a mentor who genuinely covers three of them scores
#: 3% and is buried under anyone the mapping credited with a whole career path. The question
#: worth answering is "of the handful of things this student most needs, how many can this
#: mentor help with" — which is also the sentence a student can act on.
FOCUS_GAP_COUNT = 10

#: Ceiling on coverage credited to a mentor whose skills were inferred from a study field.
#:
#: An inferred profile is the union of a career path's requirements, so it covers nearly every
#: focus gap by construction and would otherwise score a perfect match for everyone. Nobody
#: knows every skill their field asks for; capping this keeps a guess from outranking a mentor
#: who actually named what they know.
INFERRED_COVERAGE_CAP = 0.35

SIGNAL_STATED = "stated"
SIGNAL_INFERRED = "inferred"
SIGNAL_NONE = "none"

_WHITESPACE = re.compile(r"\s+")


def _normalize_field(value: str) -> str:
    return _WHITESPACE.sub(" ", (value or "").strip().lower())


@lru_cache(maxsize=1)
def _study_field_mapping() -> dict:
    """The reviewed study-field to career-path mapping, keyed by normalised field name."""
    try:
        raw = json.loads(STUDY_FIELD_CAREER_PATHS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning(
            "No study-field mapping at %s; mentors without stated expertise will rank on "
            "seniority alone", STUDY_FIELD_CAREER_PATHS_PATH,
        )
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Study-field mapping is unreadable (%s); treating it as empty", exc)
        return {}

    return {
        _normalize_field(field): paths
        for field, paths in (raw.get("mappings") or {}).items()
    }


@lru_cache(maxsize=32)
def _career_path_skill_ids(career_path: str) -> frozenset:
    """Canonical skill ids a career path requires. Empty for an unknown path."""
    try:
        rows = load_requirements(ONTOLOGY_PATH, career_path)
    except (OSError, ValueError) as exc:
        logger.warning("Could not load requirements for %r: %s", career_path, exc)
        return frozenset()
    return frozenset(row["skill_id"] for row in rows if row.get("skill_id"))


def _unmet_gaps(gap: dict) -> dict:
    """
    The student's open gaps, mapped to what closing each one is worth.

    Priority rather than raw shortfall: a small shortfall in something every posting asks for
    matters more than a large one in something almost nobody does.
    """
    unmet = {}
    for skill in gap.get("skills") or []:
        if skill.get("classification") not in UNMET_CLASSIFICATIONS:
            continue
        skill_id = skill.get("skill_id")
        if not skill_id:
            continue
        weight = skill.get("priority")
        if weight is None:
            weight = skill.get("gap", 0.0)
        unmet[skill_id] = {
            "weight": max(0.0, float(weight or 0.0)),
            "label": skill.get("label") or skill_id,
        }
    return unmet


def _stated_skill_ids(terms, matcher) -> frozenset:
    """
    Resolve free-text expertise onto canonical ids.

    Only ``accepted`` matches count. A term the matcher was unsure about is exactly the kind
    of thing that should not silently become a claim that a mentor knows a skill.
    """
    if not terms or matcher is None:
        return frozenset()

    resolved = set()
    for term in terms:
        try:
            record = matcher.match(term)
        except Exception as exc:  # noqa: BLE001 - one bad term must not fail the request
            logger.warning("Could not match expertise term %r: %s", term, exc)
            continue
        if record.get("review_status") == ACCEPTED and record.get("canonical_id"):
            resolved.add(record["canonical_id"])
    return frozenset(resolved)


def _inferred_skill_ids(study_field: str) -> frozenset:
    """Skills a graduate of this study field is assumed to know."""
    paths = _study_field_mapping().get(_normalize_field(study_field))
    if not paths:
        return frozenset()

    skills = set()
    for path in paths:
        skills |= _career_path_skill_ids(path)
    return frozenset(skills)


def _years_of_experience(field_starting_year, today=None) -> int:
    if not field_starting_year:
        return 0
    current_year = (today or date.today()).year
    return max(0, current_year - int(field_starting_year))


def _seniority(years: int) -> float:
    return min(1.0, years / SENIORITY_FULL_YEARS) if years > 0 else 0.0


def _explain(aligned, signal: str, years: int, mentor_skill_count: int) -> str:
    """
    Say why this mentor was ranked here, in terms of the student's own gaps.

    Written from the gap rather than from anything the mentor wrote about themselves — the
    platform has no mentor prose to quote, and the gap is the more useful sentence anyway.
    """
    if not aligned:
        if signal == SIGNAL_NONE:
            return (
                "No expertise on record and their study field is not mapped, so this ranking "
                "reflects experience only."
            )
        return "None of your current skill gaps overlap with this mentor's area."

    names = [item["skill_label"] for item in aligned[:3]]
    covered = ", ".join(names)
    if len(aligned) > 3:
        covered += f", and {len(aligned) - 3} more"

    if signal == SIGNAL_STATED:
        basis = f"They list expertise in {covered}"
    else:
        basis = f"Their study field usually covers {covered}"

    experience = f" with {years} years in the field" if years else ""
    return f"{basis}, which you are currently weak in{experience}."


def _focus_gaps(unmet: dict, count: int = FOCUS_GAP_COUNT) -> dict:
    """The student's highest-priority open gaps — what a mentor is actually scored against."""
    ranked = sorted(unmet.items(), key=lambda item: (-item[1]["weight"], item[0]))
    return dict(ranked[:count])


def score_mentor(mentor: dict, unmet: dict, focus: dict, matcher=None, today=None) -> dict:
    """Score one mentor against the student's highest-priority gaps."""
    stated = _stated_skill_ids(mentor.get("expertise_terms"), matcher)

    if stated:
        mentor_skills, signal, confidence = stated, SIGNAL_STATED, 1.0
    else:
        inferred = _inferred_skill_ids(mentor.get("study_field") or "")
        if inferred:
            mentor_skills, signal, confidence = inferred, SIGNAL_INFERRED, INFERRED_CONFIDENCE
        else:
            mentor_skills, signal, confidence = frozenset(), SIGNAL_NONE, 0.0

    aligned = [
        {"skill_id": skill_id, "skill_label": detail["label"]}
        for skill_id, detail in focus.items()
        if skill_id in mentor_skills
    ]
    # Most valuable gap first, so the explanation names the ones that matter.
    aligned.sort(key=lambda item: (-focus[item["skill_id"]]["weight"], item["skill_id"]))

    focus_weight = sum(detail["weight"] for detail in focus.values())
    covered_weight = sum(focus[item["skill_id"]]["weight"] for item in aligned)
    coverage = (covered_weight / focus_weight) if focus_weight > 0 else 0.0

    if signal == SIGNAL_INFERRED:
        coverage = min(coverage, INFERRED_COVERAGE_CAP)

    years = _years_of_experience(mentor.get("field_starting_year"), today)
    score = COVERAGE_WEIGHT * coverage * confidence + SENIORITY_WEIGHT * _seniority(years)

    # Reported separately from the focus set: useful context, but not what was scored.
    total_addressed = sum(1 for skill_id in unmet if skill_id in mentor_skills)

    return {
        "mentor_id": mentor["mentor_id"],
        "score": round(min(1.0, max(0.0, score)), 4),
        "signal": signal,
        "aligned_skills": aligned,
        "gaps_addressed": total_addressed,
        "years_experience": years,
        "explanation": _explain(aligned, signal, years, len(mentor_skills)),
    }


def build_mentor_matches(gap: dict, mentors, matcher=None, limit: int = 10,
                         today=None) -> dict:
    """
    Rank mentors against one student's skill gap.

    Ordering is by score, then by most gaps addressed, then by mentor id. The final key makes
    ties deterministic: without it, two equally-scored mentors could swap places between
    identical requests, which reads to a student as the ranking being arbitrary.
    """
    unmet = _unmet_gaps(gap)
    focus = _focus_gaps(unmet)

    scored = [score_mentor(mentor, unmet, focus, matcher, today) for mentor in mentors]
    scored.sort(key=lambda item: (-item["score"], -item["gaps_addressed"], item["mentor_id"]))

    return {
        "career_path": gap.get("career_path"),
        "taxonomy_version": gap.get("taxonomy_version"),
        "total": len(scored),
        "gaps_considered": len(focus),
        "items": scored[:limit],
    }
