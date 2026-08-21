"""
CareerCompass — catalog course → skill index

Tags every catalog course with the taxonomy skills it teaches, producing the
`{skill_id: [courses]}` index M4 recommends from.

**Why this does not reuse the job pipeline's matcher.** The plan was to mine
free terms and resolve them with `SkillMatcher`, as the job corpus does. The
arithmetic rules it out: 23,564 Coursera courses yield on the order of 235,000
terms, and at the measured ~1.7 s per LLM-routed term that is over 100 hours.
The job corpus made itself tractable with a document-frequency cutoff, but a
cutoff is exactly wrong here — a course teaching a niche skill is precisely
what is worth recommending, and `df >= 5` would delete it.

So the direction is reversed. Instead of asking "what does this text mention,
and which skill is that?", this asks "which of the 903 known skills does this
text name?" — an exact lookup against the alias index rather than open-ended
resolution. It runs in seconds, needs no model, and cannot invent a mapping.

The trade is recall for precision, deliberately. A course whose description
says "containerisation" in words the taxonomy does not list is missed; but a
course is never tagged with a skill it does not name. For recommendation that
is the right way round: a missing course is invisible, whereas a wrong one is
something the student opens, works through, and does not get the skill from.
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from careercompass.config import JOBS_DIR
from careercompass.skills.artifacts import cached_by_files
from careercompass.skills.phrases import NOISE_TERMS
from careercompass.skills.taxonomy import QUALIFIER_RE, normalize
from careercompass.skills.taxonomy import AliasIndex  # noqa: F401  (kept for callers)

logger = logging.getLogger(__name__)

INDEX_PATH = Path(JOBS_DIR).parent / "catalog" / "course_skills.json"

# Longest alias worth scanning for. The taxonomy's surfaces are almost all
# one to four words; going wider multiplies the n-grams for nothing.
MAX_NGRAM = 4
# A surface shorter than this matches too much to be evidence of anything.
# Two-letter names (Go, R, C) are already unreachable — MIN_TERM_LENGTH is 3
# across the whole system, recorded as a known limitation.
MIN_SURFACE = 3

# Dots, slashes and hyphens are kept because they are inside real names —
# Node.js, ASP.NET, CI/CD, scikit-learn — but that also swallows sentence
# punctuation, so "Python." arrives as one token and never matches "python".
_WORD = re.compile(r"[A-Za-z0-9+#./-]+")
_EDGE_PUNCT = re.compile(r"^[./-]+|[./-]+$")


def _tokens(text: str) -> list:
    """Words with sentence punctuation trimmed but internal punctuation kept."""
    words = []
    for raw in _WORD.findall(text or ""):
        word = _EDGE_PUNCT.sub("", raw)
        if word:
            words.append(word)
    return words


def _usable_surface(key: str) -> bool:
    """Whether a normalised surface is specific enough to scan for."""
    return (MIN_SURFACE <= len(key)
            and key not in NOISE_TERMS
            and len(key.split()) <= MAX_NGRAM)


def _is_head_noun_alias(key: str, label_key: str, label_words: set) -> bool:
    """Whether a surface is a bare head noun lifted out of its own label.

    ESCO lists aliases far broader than the skill they name: *packaging
    engineering* claims "engineering", *Microsoft Access* claims "Access",
    *communication skills* claims "communication". Left in, any course
    mentioning engineering is tagged as packaging engineering — which is
    exactly what happened, and put packaging engineering third in a catalog of
    computing courses.

    The rule: a **single-word** alias that is one of the words of the skill's
    own multi-word label is the head noun, and a head noun is never specific
    enough to identify a skill. The label itself always survives, so single-word
    skills like Docker and Python are untouched, and acronyms and product names
    that are not in the label — ML, K8s, Jenkins — survive too.

    This is the bare-category-noun failure the job corpus hit, handled by a rule
    rather than by naming words one at a time. See ENGINEERING_NOTES.md §5.
    """
    if key == label_key:
        return False
    if " " in key:
        return False
    return key in label_words and len(label_words) > 1


def build_surface_map(skills: list, skill_ids: set = None) -> dict:
    """
    ``{normalised surface: skill_id}`` over every label and alias.

    ``skill_ids`` restricts the map to skills that can actually be recommended.
    Pass the ids in the career-path ontology: a gap only ever contains those,
    so a course tagged with anything else can never surface, and every alias
    outside that set is pure false-positive surface area. Without it a computing
    catalog picks up ESCO's craft vocabulary — "patterns" is an alias of
    *manufacturing dies*, so *Design Patterns* was tagged as metalworking.

    A surface claimed by more than one skill is dropped rather than assigned
    to whichever came first: an ambiguous tag is worse than no tag, and the
    taxonomy merge already showed how quietly a wrong id spreads.
    """
    # Tracked separately because a skill's own label outranks another skill's
    # alias for the same string. "CSS" is the label of CSS and merely an alias
    # of "style sheet languages"; treating both claims as equal dropped the
    # surface entirely, and CSS — asked for by 14% of Backend postings —
    # matched none of 14,941 courses. The matcher has always resolved this the
    # same way; only this map did not.
    by_label = defaultdict(set)
    by_alias = defaultdict(set)

    for skill in skills:
        if skill_ids is not None and skill["id"] not in skill_ids:
            continue
        label_key = normalize(skill["label"])
        label_words = set(label_key.split())

        # A parenthetical qualifier disambiguates for a human reader; it is not
        # part of the name. "Ruby (computer programming)" is called Ruby, and
        # without this it could only ever be matched by its full ESCO label,
        # which no course title uses.
        label_surfaces = {skill["label"], QUALIFIER_RE.sub(" ", skill["label"])}

        for surface in label_surfaces:
            key = normalize(surface)
            if _usable_surface(key):
                by_label[key].add(skill["id"])

        for surface in skill.get("aliases") or []:
            key = normalize(surface)
            if not _usable_surface(key):
                continue
            if _is_head_noun_alias(key, label_key, label_words):
                continue
            by_alias[key].add(skill["id"])

    surface_map, ambiguous = {}, 0
    for key in set(by_label) | set(by_alias):
        owners = by_label.get(key) or by_alias.get(key) or set()
        if len(owners) == 1:
            surface_map[key] = next(iter(owners))
        else:
            ambiguous += 1

    if ambiguous:
        logger.info("surface map: %d surfaces dropped as ambiguous", ambiguous)
    return surface_map


def skills_in_text(text: str, surface_map: dict) -> set:
    """Every skill id whose label or alias appears in the text."""
    words = _tokens(text)
    found = set()
    for size in range(1, MAX_NGRAM + 1):
        for i in range(len(words) - size + 1):
            key = normalize(" ".join(words[i:i + size]))
            skill_id = surface_map.get(key)
            if skill_id:
                found.add(skill_id)
    return found


def build_index(courses: list, taxonomy, *, min_skills: int = 1,
                skill_ids: set = None) -> dict:
    """
    Tag courses and invert into ``{skill_id: [course records]}``.

    Args:
        courses: ``catalog.base.Course`` records.
        taxonomy: a loaded ``Taxonomy``.
        min_skills: drop courses tagging fewer skills than this. A course
            naming nothing in the taxonomy cannot be recommended for anything.
        skill_ids: restrict tagging to these skills — normally every id in the
            career-path ontology. See ``build_surface_map``.

    Returns:
        ``{skill_id: [{course_id, platform, title, url, level, language,
        duration_hours, rating}]}`` — note that no description is carried
        through. It was read to produce the tags and is dropped here, which is
        the only place that guarantee is enforced.
    """
    surface_map = build_surface_map(taxonomy.skills, skill_ids)
    logger.info("surface map: %d unambiguous surfaces", len(surface_map))

    index = defaultdict(list)
    tagged = 0

    for course in courses:
        # Tagged separately so the two can be told apart. A course that names a
        # skill in its title is about that skill; one that names it in the
        # description may only be mentioning it in passing — "runs on Windows,
        # macOS and Linux" is not a Linux course, and "HTML5: Content Authoring
        # Fundamentals" was being recommended to close a Linux gap.
        in_title = skills_in_text(course.title, surface_map)
        in_body = skills_in_text(course.description, surface_map)
        # Not `skill_ids`: that is this function's argument, and rebinding it
        # here leaves the next reader with a parameter that silently holds the
        # last course's tags.
        course_skill_ids = in_title | in_body
        if len(course_skill_ids) < min_skills:
            continue
        tagged += 1
        base = {
            "course_id": course.course_id,
            "platform": course.platform,
            "title": course.title,
            "url": course.url,
            "level": course.level,
            "language": course.language,
            "duration_hours": course.duration_hours,
            "rating": course.rating,
        }
        for skill_id in course_skill_ids:
            index[skill_id].append({**base, "in_title": skill_id in in_title})

    logger.info("indexed %d of %d courses across %d skills",
                tagged, len(courses), len(index))
    return dict(index)


def ontology_skill_ids(path=None) -> set:
    """Every skill id any career path requires — the only ones worth indexing."""
    from careercompass.skills.ontology import ONTOLOGY_PATH, load_ontology

    rows = load_ontology(path or ONTOLOGY_PATH)
    return {row["skill_id"] for row in rows if row.get("skill_id")}


def save_index(index: dict, path=INDEX_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_skills": len(index),
        "total_courses": len({c["course_id"] for courses in index.values()
                              for c in courses}),
        "WARNING": "Course descriptions are deliberately absent. The catalog "
                   "copyright belongs to the platforms and their partners, and "
                   "no licence to republish them is granted. Link out instead.",
        "skills": index,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@cached_by_files(lambda path=INDEX_PATH: [path])
def load_index(path=INDEX_PATH) -> dict:
    """The `{skill_id: [courses]}` index M4 recommends from.

    Cached on the index file's fingerprint. This is a 14.2 MB parse that
    `/api/v1/recommendations` was paying on every single call — 82 ms and 71 MB
    of transient allocation for a file only `build_course_catalog` ever writes.
    """
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("skills", {})
