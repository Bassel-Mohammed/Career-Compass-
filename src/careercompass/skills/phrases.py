"""
CareerCompass — Phrase Mining

The part of skill extraction that is about English rather than about
documents: split a line of prose into the skill phrases it names, and trim
each one down to the skill itself.

Both extractors need this. A syllabus writes "Design and implement a
robotics system using ROS 2, Gazebo and RViz" and a job posting writes
"Design, develop and maintain web applications using Spring Boot" — the
same splitting on connectives, the same leading-verb stripping, the same
rejection of filler. What differs is the surrounding structure: a syllabus
has learning outcomes and weekly schedules, a posting has requirement and
responsibility sections. That structure stays in the two extractors, which
supply their own prefixes and heading patterns through the parameters
here.

Usage:
    from careercompass.skills.phrases import phrases, add_mention

    for term in phrases("Design and implement RESTful APIs using Flask"):
        add_mention(found, term, "requirements", "advanced", evidence)
"""

import re

# ── Levels ─────────────────────────────────────────────────────
#
# Action verbs graded by the depth they imply. A syllabus uses these as
# Bloom's taxonomy to level a learning outcome; both extractors use them
# to recognise and strip the verb that opens a phrase, because the verb
# states the depth, not the skill.
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

# ── Phrase Patterns ────────────────────────────────────────────

PAREN_RE = re.compile(r"\(([^)]*)\)")
LEADING_LIST_MARKER_RE = re.compile(
    r"^\s*(?:(?:[-*]\s+)|(?:[–—]\s*)|"
    r"(?:[·•‣⁃∙■▪▫○●◦]\s*))+"
)

# Fragment separators. Splitting on these turns "sensing, acting, planning,
# and learning" into four candidates.
SPLIT_RE = re.compile(
    r"\s*(?:[,;:&]|\.\s|\.$|\band\b|\bor\b|\bfor\b|\bincluding\b|\bsuch as\b)\s*",
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

# Syllabus scaffolding: the administrative furniture of a course schedule.
# Exact matches only, deliberately. A suffix rule that stripped "overview" or
# "introduction" would also delete "IEEE 802.11 standards overview" and
# "instruction set architecture overview", which are real skills wearing a
# scaffolding word - and "code review" and "database design review" are skills
# outright. Only phrases that carry no skill content at all belong here.
SYLLABUS_NOISE_TERMS = NOISE_TERMS | {
    "presentation", "presentations", "final presentation",
    "final project", "final project development", "final project planning",
    "final project review", "final project presentation",
    "final project presentations", "final project demonstration",
    "final project implementation", "final project overview",
    "final project lab", "final project showcase",
    "project development", "project planning", "project presentation",
    "capstone project", "capstone project planning",
    "capstone project kickoff", "capstone project implementation",
    "course review", "course wrap-up", "course wrap up", "course conclusion",
    "final review", "final preparation", "final exam preparation",
    "final deliverable verification", "final assessment",
    "midterm exam", "midterm review", "midterm preparation",
    "exam preparation", "revision", "recap", "wrap-up", "wrap up",
    "guest lecture", "seminar", "student presentations",
}

MIN_TERM_LENGTH = 3
MAX_TERM_WORDS = 6


# ── Phrase Helpers ─────────────────────────────────────────────
def strip_parentheticals(text: str) -> tuple:
    """
    Pull parenthesized content out of a phrase.

    Parentheses hold acronyms and sub-lists — "human-robot interaction
    (HRI)", "(Files and RQT Tool)" — which are skills in their own right
    but wreck a naive split if left inline.
    """
    inner = [match.strip() for match in PAREN_RE.findall(text) if match.strip()]
    return PAREN_RE.sub(" ", text), inner


def strip_unmatched_parentheses(text: str) -> str:
    """Remove only unpaired parentheses while preserving their contents."""
    openings = []
    unmatched = set()
    for index, character in enumerate(text):
        if character == "(":
            openings.append(index)
        elif character == ")":
            if openings:
                openings.pop()
            else:
                unmatched.add(index)
    unmatched.update(openings)
    if not unmatched:
        return text
    return "".join(" " if index in unmatched else character
                   for index, character in enumerate(text))


def strip_leading_verb(text: str) -> str:
    """
    Drop the action verb that opens a phrase.

    "Design and Implement a Robotics system ..." states the depth of the
    outcome, not the skill; the skill is what follows. The same holds for
    a responsibility bullet: "Build and maintain CI/CD pipelines".
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


def clean_fragment(fragment: str) -> str:
    """
    Trim a split fragment down to the skill it names.

    Strips punctuation, articles and connectives from both ends, and drops
    a leading action verb: "and Define human-robot interaction" splits out
    of a learning outcome still carrying its verb.
    """
    fragment = LEADING_LIST_MARKER_RE.sub("", fragment)
    term = TRAIL_RE.sub("", fragment.strip())
    previous = None
    while term and term != previous:
        previous = term
        term = strip_leading_verb(term)
        term = LEAD_RE.sub("", term).strip()
        term = TRAIL_WORD_RE.sub("", term)
        term = TRAIL_RE.sub("", term)
    return re.sub(r"\s+", " ", term)


def is_usable(term: str, *, reject=(), noise_terms=NOISE_TERMS) -> bool:
    """
    Reject residue, filler and phrases too long to be a single skill.

    Args:
        term: The cleaned candidate.
        reject: Patterns that disqualify the term when they match it
            whole — a caller's structural headings.
        noise_terms: Lowercased phrases that are never a skill.
    """
    term = term.strip()
    if any(pattern.fullmatch(term) for pattern in reject):
        return False
    if len(term) < MIN_TERM_LENGTH:
        return False
    if term.lower() in noise_terms:
        return False
    words = term.split()
    if len(words) > MAX_TERM_WORDS:
        return False
    # A lone possessive is the head of a phrase whose noun wrapped away
    # ("Robot's" / "Sensors" split across two schedule rows).
    if len(words) == 1 and re.search(r"['’]s$", term):
        return False
    # Must contain at least two letters; drops stray numbers and symbols but
    # retains technology compounds whose letters are separated ("C/C++").
    return len(re.findall(r"[A-Za-z]", term)) >= 2


def phrases(text: str, *, prefix_rounds=(), reject_lines=(), reject_terms=(),
            noise_terms=NOISE_TERMS) -> list:
    """
    Split a line of prose into candidate skill phrases.

    Args:
        text: One line — a learning outcome, a schedule row, a bullet.
        prefix_rounds: Sequences of patterns to strip from the front, applied
            in order. `reject_lines` is re-tested after each round, because
            stripping a prefix can expose a heading: "Week 3: Final Exam"
            only looks like an exam row once "Week 3:" is gone.
        reject_lines: Patterns that discard the whole line when they match
            what remains of it.
        reject_terms: Patterns that discard an individual candidate.
        noise_terms: Lowercased phrases that are never a skill.

    Returns:
        The candidate phrases, in the order they appeared.
    """
    if not text:
        return []
    text = LEADING_LIST_MARKER_RE.sub("", text)

    for patterns in prefix_rounds:
        for pattern in patterns:
            text = pattern.sub("", text)
        if any(p.fullmatch(text.strip()) for p in reject_lines):
            return []

    body, inner = strip_parentheticals(strip_unmatched_parentheses(text))
    terms = []
    for chunk in [body] + inner:
        for fragment in SPLIT_RE.split(chunk):
            term = clean_fragment(fragment)
            if is_usable(term, reject=reject_terms, noise_terms=noise_terms):
                terms.append(term)
    return terms


# ── Accumulation ───────────────────────────────────────────────
def add_mention(found: dict, term: str, source: str, level: str,
                evidence: dict) -> None:
    """
    Record one mention, merging into an existing skill when seen before.

    `found` is keyed on the lowercased term, and the entry keeps the
    deepest level any zone claimed for the skill: a course that defines a
    concept in week 2 and builds with it in week 9 teaches it at the
    deeper of the two.
    """
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

    if LEVEL_RANK[level] > LEVEL_RANK[entry["level"]]:
        entry["level"] = level
    if source not in entry["sources"]:
        entry["sources"].append(source)
    entry["evidence_count"] += 1
    entry["evidence"].append(evidence)


def finalize(found: dict, source_weights: dict) -> list:
    """
    Score the accumulated mentions and order them strongest first.

    A skill's weight starts at the best zone that mentioned it and gains a
    little for each repeat, capped at 1.0 — repetition is corroboration,
    but a term named five times in a weak zone should not outrank one
    stated once in the strongest.
    """
    for entry in found.values():
        base = max(source_weights[s] for s in entry["sources"])
        repetition = 0.1 * (entry["evidence_count"] - 1)
        entry["weight"] = round(min(1.0, base + repetition), 2)

    return sorted(
        found.values(),
        key=lambda e: (-e["weight"], -e["evidence_count"], e["term"].lower()),
    )
