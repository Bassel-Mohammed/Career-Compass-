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

Usage:
    from careercompass.parsing.syllabus import parse_syllabus
    from careercompass.skills.extractor import extract_skills

    skills = extract_skills(parse_syllabus("Robotics Syl.pdf"))
"""

import re
import json
from pathlib import Path

# ── Levels ─────────────────────────────────────────────────────

# The JNQF descriptor column states the depth of an outcome directly.
JNQF_LEVELS = {
    "knowledge": "beginner",
    "skill": "intermediate",
    "competency": "advanced",
}

# Used when no descriptor is marked: the leading Bloom verb of the outcome
# grades it instead.
BLOOM_LEVELS = {
    "beginner": (
        "define", "describe", "list", "identify", "recognize", "state",
        "explain", "discuss", "understand", "survey", "explore", "review",
        "consider", "engage", "study", "cover",
    ),
    "intermediate": (
        "analyze", "demonstrate", "select", "apply", "calculate", "compute",
        "implement", "use", "perform", "compare", "examine", "solve",
        "practice", "integrate", "build",
    ),
    "advanced": (
        "design", "develop", "create", "evaluate", "troubleshoot", "resolve",
        "assess", "critique", "optimize", "investigate",
    ),
}
VERB_LEVELS = {
    verb: level for level, verbs in BLOOM_LEVELS.items() for verb in verbs
}
LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}

# How much a mention is worth, by the zone it was found in.
SOURCE_WEIGHTS = {"clo": 1.0, "lab": 0.8, "topic": 0.7, "description": 0.6}

# ── Phrase Patterns ────────────────────────────────────────────

LAB_PREFIX_RE = re.compile(r"^Lab\s*\d*\s*[:.\-]\s*", re.IGNORECASE)
PAREN_RE = re.compile(r"\(([^)]*)\)")

# Fragment separators. Splitting on these turns "sensing, acting, planning,
# and learning" into four candidates.
SPLIT_RE = re.compile(
    r"\s*(?:[,;:/&]|\.\s|\.$|\band\b|\bor\b|\bfor\b|\bincluding\b|\bsuch as\b)\s*",
    re.IGNORECASE,
)

# Connectives and qualifiers that survive splitting and must be trimmed off
# the front of a fragment before it can be a skill.
LEAD_RE = re.compile(
    r"^(?:the|a|an|to|of|for|in|on|with|by|from|its|their|various|basic|common|"
    r"other|related to|involving|using|based|key|concepts? of|types? of|"
    r"introduction to|steps? in|applications? of|problems? related to|beyond)\s+",
    re.IGNORECASE,
)
TRAIL_RE = re.compile(r"[\s.,;:&\-–]+$")

# Dangling words left at the end of a fragment once it has been split.
TRAIL_WORD_RE = re.compile(
    r"\s+(?:of|for|to|and|or|in|on|with|by|from|the|a|an|its|their|"
    r"problems?|tasks?|concepts?|throughout)$",
    re.IGNORECASE,
)

# Form bookkeeping some syllabi append to the outcome text itself
# ("Calculate statistical measures. CLO Coverage: 40%").
BOOKKEEPING_RE = re.compile(r"\bCLO\s+Coverage\b.*$", re.IGNORECASE)

# Whole rows that are administrative, not teaching content.
ADMIN_RE = re.compile(
    r"mid-?\s?term|final\s+exam|midterm\s+exam|project\s+presentation|"
    r"course\s+syllabus|presentation\s+and\s+discussion",
    re.IGNORECASE,
)

# Fragments that are grammatical residue or academic filler rather than
# anything a job posting would ever ask for.
NOISE_TERMS = {
    "course", "courses", "the course", "syllabus", "discussion", "introduction",
    "review", "concepts", "concept", "examples", "example", "components",
    "component", "applications", "application", "problems", "problem",
    "tasks", "task", "systems", "system", "methods", "method", "topics",
    "topic", "project", "projects", "exam", "exams", "quiz", "quizzes",
    "lab", "labs", "lecture", "lectures", "week", "generation", "tracking",
    "considerations", "practical considerations", "essentials", "workspace",
    "getting started", "overview", "basics", "fundamentals", "principles",
    "types", "rules", "steps", "approach", "study", "studies", "analysis",
    "theory", "practice", "laws", "law", "tool", "tools", "files", "file",
    "others", "etc", "and", "or",
    # Bare modifiers, stranded when a shared head noun is elided
    # ("Internal and External Sensors" leaves "Internal" behind).
    "internal", "external", "legged", "wheeled", "mobile", "basic", "advanced",
    "adaptive", "dynamic", "practical", "theoretical", "custom", "beyond",
    "core", "general", "special", "modern", "several", "reactive",
}

MIN_TERM_LENGTH = 3
MAX_TERM_WORDS = 6


# ── Phrase Helpers ─────────────────────────────────────────────
def _strip_parentheticals(text: str) -> tuple:
    """
    Pull parenthesized content out of a phrase.

    Parentheses in these syllabi hold acronyms and sub-lists — "human-robot
    interaction (HRI)", "(Files and RQT Tool)" — which are skills in their
    own right but wreck a naive split if left inline.
    """
    inner = [match.strip() for match in PAREN_RE.findall(text) if match.strip()]
    return PAREN_RE.sub(" ", text), inner


def _clean_fragment(fragment: str) -> str:
    """
    Trim a split fragment down to the skill it names.

    Strips punctuation, articles and connectives from both ends, and drops
    a leading Bloom verb: "and Define human-robot interaction" splits out
    of a learning outcome still carrying its verb.
    """
    term = TRAIL_RE.sub("", fragment.strip())
    previous = None
    while term and term != previous:
        previous = term
        term = _strip_leading_verb(term)
        term = LEAD_RE.sub("", term).strip()
        term = TRAIL_WORD_RE.sub("", term)
        term = TRAIL_RE.sub("", term)
    return re.sub(r"\s+", " ", term)


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


def _is_usable(term: str) -> bool:
    """Reject residue, filler and phrases too long to be a single skill."""
    if len(term) < MIN_TERM_LENGTH:
        return False
    if term.lower() in NOISE_TERMS:
        return False
    words = term.split()
    if len(words) > MAX_TERM_WORDS:
        return False
    # A lone possessive is the head of a phrase whose noun wrapped away
    # ("Robot's" / "Sensors" split across two schedule rows).
    if len(words) == 1 and re.search(r"['’]s$", term):
        return False
    # Must contain at least one letter; drops stray numbers and symbols.
    return bool(re.search(r"[A-Za-z]{2}", term))


def _phrases(text: str) -> list:
    """Split a line of syllabus text into candidate skill phrases."""
    if not text or ADMIN_RE.search(text):
        return []

    body, inner = _strip_parentheticals(text)
    terms = []
    for chunk in [body] + inner:
        for fragment in SPLIT_RE.split(chunk):
            term = _clean_fragment(fragment)
            if _is_usable(term):
                terms.append(term)
    return terms


def _strip_leading_verb(text: str) -> str:
    """
    Drop the Bloom verb that opens a learning outcome.

    "Design and Implement a Robotics system ..." states the depth of the
    outcome, not the skill; the skill is what follows.
    """
    words = text.split()
    index = 0
    while index < len(words):
        word = re.sub(r"[^A-Za-z\-]", "", words[index]).lower()
        if word in VERB_LEVELS:
            index += 1
            # Skip a conjunction joining two verbs ("Design and Implement").
            if index < len(words) and words[index].lower() in ("and", "or", "&"):
                index += 1
            continue
        break
    return " ".join(words[index:])


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
def _add(found: dict, term: str, source: str, level: str, evidence: dict) -> None:
    """Record one mention, merging into an existing skill when seen before."""
    key = term.lower()
    entry = found.get(key)
    if entry is None:
        entry = {
            "term": term,
            "canonical": None,
            "level": level,
            "weight": 0.0,
            "evidence_count": 0,
            "sources": [],
            "evidence": [],
        }
        found[key] = entry

    # Keep the deepest level any zone claims for this skill.
    if LEVEL_RANK[level] > LEVEL_RANK[entry["level"]]:
        entry["level"] = level
    if source not in entry["sources"]:
        entry["sources"].append(source)
    entry["evidence_count"] += 1
    entry["evidence"].append(evidence)


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
        body = _strip_leading_verb(BOOKKEEPING_RE.sub("", clo["text"]))
        for term in _phrases(body):
            _add(found, term, "clo", level, {
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
                    _add(found, term, source, level, {
                        "source": source,
                        "week": week["week"],
                        "text": line,
                    })

    for term in _phrases(syllabus.get("description", "")):
        _add(found, term, "description", "beginner", {
            "source": "description",
            "text": term,
        })

    for entry in found.values():
        base = max(SOURCE_WEIGHTS[s] for s in entry["sources"])
        repetition = 0.1 * (entry["evidence_count"] - 1)
        entry["weight"] = round(min(1.0, base + repetition), 2)

    return sorted(
        found.values(),
        key=lambda e: (-e["weight"], -e["evidence_count"], e["term"].lower()),
    )


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
