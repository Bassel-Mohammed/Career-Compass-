"""Shared record shape and helpers for every catalog source."""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from careercompass.config import RAW_DATA_DIR

CATALOG_DIR = Path(RAW_DATA_DIR) / "catalog"

# Beginner/intermediate/advanced, inferred from the title when a source does
# not say. Level fit is half of what makes a recommendation useful — an
# advanced course for a skill the student has never studied is not advice.
_BEGINNER = re.compile(
    r"\b(introduction|introductory|intro|beginner|beginners|basics|fundamentals|"
    r"getting started|foundations?|essentials|101|for beginners|primer)\b", re.I)
_ADVANCED = re.compile(
    r"\b(advanced|expert|mastery|masterclass|in depth|in-depth|deep dive|"
    r"professional certificate|specialization|capstone)\b", re.I)


@dataclass
class Course:
    """One catalog entry, normalised across sources."""

    course_id: str
    platform: str
    title: str
    url: str
    description: str = ""          # transient: never persisted, see __init__ docstring
    level: str | None = None
    language: str | None = None
    duration_hours: float | None = None
    rating: float | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def matchable_text(self) -> str:
        """Title plus description, the text the skill matcher reads."""
        return f"{self.title}. {self.description}".strip()


def infer_level(title: str, given: str = None) -> str | None:
    """Use the source's own level when it has one, else read it off the title."""
    if given:
        given = given.strip().lower()
        for level in ("beginner", "intermediate", "advanced"):
            if level in given:
                return level
    if _ADVANCED.search(title or ""):
        return "advanced"
    if _BEGINNER.search(title or ""):
        return "beginner"
    return None


def normalise(records: list) -> list:
    """Drop entries missing the two fields nothing downstream can work without.

    A course with no URL cannot be recommended — the design requires every item
    carry a real link — and one with no title cannot be matched or displayed.
    """
    keep = []
    for course in records:
        if not (course.url or "").strip():
            continue
        if not (course.title or "").strip():
            continue
        keep.append(course)
    return keep


def save_raw(platform: str, courses: list) -> Path:
    """Cache a pull so re-matching never needs a re-fetch.

    Written under data/raw/catalog/, which is git-ignored: this is the only
    place descriptions live, and they are not ours to redistribute.
    """
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    path = CATALOG_DIR / f"{platform}.json"
    payload = {"platform": platform, "total": len(courses),
               "courses": [c.to_dict() for c in courses]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_raw(platform: str) -> list:
    """Read a cached pull back as Course records."""
    path = CATALOG_DIR / f"{platform}.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Course(**record) for record in payload.get("courses", [])]
