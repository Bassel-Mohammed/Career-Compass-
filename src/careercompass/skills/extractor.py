"""
CareerCompass — Course Syllabus Skill Extractor

Turns the structured output of syllabus_parser into a weighted, levelled
list of candidate skills for a course.

This is the deterministic half of skill extraction. It mines skill phrases
out of the four zones a syllabus carries and grades each one:

    - Course Learning Outcomes  the strongest signal; the form already
                                classifies each outcome as knowledge,
                                skill or competency
    - Lab sessions              concrete tools ("GazeboSim Harmonic")
    - Weekly topics             subject matter
    - Course description        recall, lowest precision

Each skill carries the evidence it was drawn from, so a later pass can
audit it. Terms are left as they appear in the syllabus; mapping them onto
a shared vocabulary is the job of the taxonomy pass, which fills in the
"canonical" field this module leaves as None.

The phrase-level work — splitting a line into candidates and trimming each
one — lives in careercompass.skills.phrases, which the job-posting
extractor shares. What stays here is what makes a syllabus a syllabus:
learning outcomes, weekly schedules, and the JNQF and Bloom vocabulary
that levels them.

Usage:
    from careercompass.parsing.syllabus import parse_syllabus
    from careercompass.skills.extractor import extract_skills

    skills = extract_skills(parse_syllabus("robotics_programming.pdf"))
"""

import re
import json
from pathlib import Path

from careercompass.skills.phrases import (
    BLOOM_LEVELS, LEADING_LIST_MARKER_RE, LEAD_RE, LEVEL_RANK,
    MAX_TERM_WORDS, MIN_TERM_LENGTH, NOISE_TERMS, PAREN_RE, SPLIT_RE,
    SYLLABUS_NOISE_TERMS,
    TRAIL_RE, TRAIL_WORD_RE, VERB_LEVELS, add_mention, clean_fragment,
    finalize, is_usable, phrases, strip_leading_verb, strip_parentheticals,
    strip_unmatched_parentheses,
)

# ── Levels ─────────────────────────────────────────────────────

# The JNQF descriptor column states the depth of an outcome directly.
JNQF_LEVELS = {
    "knowledge": "beginner",
    "skill": "intermediate",
    "competency": "advanced",
}

# How much a mention is worth, by the zone it was found in.
SOURCE_WEIGHTS = {"clo": 1.0, "lab": 0.8, "topic": 0.7, "description": 0.6}

# ── Syllabus Structure ─────────────────────────────────────────

LAB_PREFIX_RE = re.compile(r"^Lab\s*\d*\s*[:.\-]\s*", re.IGNORECASE)

# Form bookkeeping some syllabi append to the outcome text itself
# ("Calculate statistical measures. CLO Coverage: 40%").
BOOKKEEPING_RE = re.compile(r"\bCLO\s+Coverage\b.*$", re.IGNORECASE)

# Whole rows that are administrative, not teaching content.  These are
# anchored so "Final Exam: recursion" can still contribute "recursion".
EXAM_HEADING_RE = re.compile(
    r"^(?:(?:mid(?:[-\s]?(?:term|semester))?|final)"
    r"(?:[-\s]+exam(?:ination)?)?(?:\s*/\s*project)?|"
    r"mid(?:[-\s]?term)?\s*/\s*final(?:[-\s]+exam(?:ination)?)?|"
    r"(?:comprehensive\s+)?review\s*(?:&|and)\s*final"
    r"(?:\s+exam(?:ination)?)?)$",
    re.IGNORECASE,
)
ADMIN_HEADING_RE = re.compile(
    r"^(?:course\s+syllabus(?:\s+discussion)?|"
    r"project\s+presentation(?:\s*(?:&|and)\s*discussion)?|"
    r"presentation\s*(?:&|and)\s*discussion)$",
    re.IGNORECASE,
)
CHAPTER_LABEL_RE = re.compile(
    r"^(?:chapters?|ch\.?)\s+[0-9ivxlcdm]+"
    r"(?:\s*(?:[-–—,&/]|and)\s*[0-9ivxlcdm]+)*$",
    re.IGNORECASE,
)
CHAPTER_PREFIX_RE = re.compile(
    r"^(?:chapters?|ch\.?)\s+[0-9ivxlcdm]+"
    r"(?:\s*(?:[-–—,&/]|and)\s*[0-9ivxlcdm]+)*\s*[:–—-]\s*",
    re.IGNORECASE,
)
EXAM_PREFIX_RE = re.compile(
    r"^(?:(?:mid|final)[-\s]+exam(?:ination)?|"
    r"mid[-\s]?(?:term|semester)(?:[-\s]+exam(?:ination)?)?)"
    r"\s*[:–—-]\s*",
    re.IGNORECASE,
)

# A lab prefix goes first; the chapter and exam prefixes are stripped only
# after the line has been tested as a heading, so "Final Exam" is dropped
# whole while "Final Exam: recursion" keeps its topic.
SYLLABUS_PREFIX_ROUNDS = (
    (LAB_PREFIX_RE,),
    (CHAPTER_PREFIX_RE, EXAM_PREFIX_RE),
)
SYLLABUS_REJECT_LINES = (EXAM_HEADING_RE, ADMIN_HEADING_RE)
SYLLABUS_REJECT_TERMS = (EXAM_HEADING_RE, ADMIN_HEADING_RE, CHAPTER_LABEL_RE)


# ── Phrase Helpers ─────────────────────────────────────────────
def _phrases(text: str) -> list:
    """Split a line of syllabus text into candidate skill phrases."""
    return phrases(
        text,
        prefix_rounds=SYLLABUS_PREFIX_ROUNDS,
        reject_lines=SYLLABUS_REJECT_LINES,
        reject_terms=SYLLABUS_REJECT_TERMS,
        noise_terms=SYLLABUS_NOISE_TERMS,
    )


def _join_wrapped(lines: list) -> list:
    """
    Rejoin schedule lines that are one phrase wrapped across two rows.

    "Position control of manipulators; Control" / "laws;" is one topic
    broken by the cell width, whereas "(Concepts & Examples)" / "Mobile
    robot Kinematics" are two. A line that opens with a lowercase letter
    continues the one above it; anything else starts a new topic.
    """
    joined = []
    for line in lines:
        if joined and line[:1].islower():
            joined[-1] = f"{joined[-1]} {line}"
        else:
            joined.append(line)
    return joined


# ── Level Resolution ───────────────────────────────────────────
def _clo_level(clo: dict) -> str:
    """Resolve a learning outcome to a proficiency level."""
    descriptor = clo.get("jnqf_descriptor")
    if descriptor in JNQF_LEVELS:
        return JNQF_LEVELS[descriptor]
    verb = (clo.get("bloom_verb") or "").lower()
    return VERB_LEVELS.get(verb, "beginner")


def _week_level(week: dict, clo_levels: dict) -> str:
    """
    Resolve a week to a level from the outcomes it is marked against.

    A lab or topic carries no descriptor of its own, so it inherits the
    deepest level among the CLOs the schedule links it to.
    """
    levels = [clo_levels[n] for n in week.get("clos", []) if n in clo_levels]
    if not levels:
        return "beginner"
    return max(levels, key=lambda level: LEVEL_RANK[level])


# ── Extraction ─────────────────────────────────────────────────
def extract_skills(syllabus: dict) -> list:
    """
    Extract candidate skills from a parsed syllabus.

    Args:
        syllabus: The dictionary returned by syllabus_parser.parse_syllabus.

    Returns:
        List of skill dictionaries, strongest first, each with:
            term            the phrase as it appears in the syllabus
            canonical       None until the taxonomy pass resolves it
            level           beginner | intermediate | advanced
            weight          0.0-1.0 confidence, from zone and repetition
            evidence_count  how many mentions backed it
            sources         which zones mentioned it
            evidence        every mention, for auditing
    """
    found = {}
    clo_levels = {}

    for clo in syllabus.get("clos", []):
        level = _clo_level(clo)
        clo_levels[clo["number"]] = level
        body = strip_leading_verb(BOOKKEEPING_RE.sub("", clo["text"]))
        for term in _phrases(body):
            add_mention(found, term, "clo", level, {
                "source": "clo",
                "clo": clo["number"],
                "text": clo["text"],
            })

    for week in syllabus.get("weeks", []):
        level = _week_level(week, clo_levels)
        for source, lines in (("lab", week.get("labs", [])),
                              ("topic", _join_wrapped(week.get("topics", [])))):
            for line in lines:
                text = LAB_PREFIX_RE.sub("", line) if source == "lab" else line
                for term in _phrases(text):
                    add_mention(found, term, source, level, {
                        "source": source,
                        "week": week["week"],
                        "text": line,
                    })

    for term in _phrases(syllabus.get("description", "")):
        add_mention(found, term, "description", "beginner", {
            "source": "description",
            "text": term,
        })

    return finalize(found, SOURCE_WEIGHTS)


def save_skills(course_code: str, skills: list, output_path: str, extra: dict = None) -> None:
    """
    Save extracted skills to a JSON file.

    Args:
        course_code: The course these skills belong to.
        skills: The extracted skill dictionaries.
        output_path: Where to write the JSON.
        extra: Optional top-level fields to record alongside the skills,
            used by the taxonomy pass to store its match summary.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "course_code": course_code,
        "total_skills": len(skills),
        **(extra or {}),
        "skills": skills,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved skills to: {output_path}")
