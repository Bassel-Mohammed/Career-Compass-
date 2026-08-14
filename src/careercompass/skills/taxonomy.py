"""
CareerCompass — Canonical Skill Taxonomy

The shared vocabulary every other module speaks. Syllabus skills and job
skills only line up if both are resolved onto the same identifiers, so this
module owns:

    - the record shape a canonical skill has, whatever source it came from
    - text normalisation, so "ROS2", "ros 2" and "Robot Operating System"
      collapse onto one lookup key
    - the alias index the matcher's exact-lookup stage reads
    - loading and saving the merged taxonomy file

Three sources feed it (see taxonomy_sources.py for the ingestion):

    esco    the backbone; multilingual, stable concept URIs, links to
            occupations
    onet    software, tools and transferable skills ESCO under-covers
    custom  technology the public taxonomies simply do not carry
            ("ROS 2 node development", "GazeboSim Harmonic")

Usage:
    from careercompass.skills.taxonomy import load_taxonomy, AliasIndex

    taxonomy = load_taxonomy()
    index = AliasIndex(taxonomy.skills)
    hit = index.lookup("ROS2")
"""

import re
import json
import hashlib
import logging
import unicodedata
from pathlib import Path

from careercompass.config import (
    CUSTOM_SKILLS_PATH, TAXONOMY_CACHE_DIR, TAXONOMY_DIR, TAXONOMY_PATH,
)

# ── Layout ─────────────────────────────────────────────────────
# Re-exported so callers can keep importing them from here, but owned by
# careercompass.config, which resolves them from the package rather than
# from whatever directory the process happened to start in.

CACHE_DIR = TAXONOMY_CACHE_DIR
MERGED_PATH = TAXONOMY_PATH

# Bumped whenever the record shape or the merge rules change, so a stored
# match can be traced back to the vocabulary that produced it.
TAXONOMY_VERSION = "1.0"

# Which source wins when two of them describe the same thing. ESCO carries
# the stable public identifier, so it outranks the local additions.
SOURCE_RANK = {"esco": 3, "onet": 2, "custom": 1}

VALID_SOURCES = tuple(SOURCE_RANK)
VALID_TYPES = ("knowledge", "skill", "tool", "soft")


# ── Normalisation ──────────────────────────────────────────────

# Arabic short vowels and tatweel: decoration that changes the bytes but
# not the word, and ESCO's Arabic labels are inconsistent about them.
ARABIC_MARKS_RE = re.compile(r"[ؐ-ًؚ-ٰٟـ]")

# Everything that is not a letter, digit or one of the characters that
# carry meaning inside a technology name ("C++", "C#", "node.js").
PUNCT_RE = re.compile(r"[^\w\s+#.]", re.UNICODE)
SPACE_RE = re.compile(r"\s+")

# Words that add no discriminating power to a skill phrase.
STOPWORDS = frozenset({
    "a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or",
    "by", "from", "its", "their", "at", "as", "is", "are",
})


def normalize(text: str) -> str:
    """
    Reduce a label to its comparable form.

    Unicode is folded to NFKC so the compatibility forms ESCO emits match
    what a syllabus PDF produces, Arabic diacritics are dropped, and
    punctuation that only separates words is replaced with a space.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = ARABIC_MARKS_RE.sub("", text)
    text = PUNCT_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def _singularize(token: str) -> str:
    """Fold a trivial English plural ("sensors" -> "sensor")."""
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokens(text: str, drop_stopwords: bool = True) -> list:
    """Split normalised text into comparable tokens."""
    words = [w for w in normalize(text).split() if w]
    if drop_stopwords:
        words = [w for w in words if w not in STOPWORDS]
    return [_singularize(w) for w in words]


def key_forms(text: str) -> set:
    """
    Every lookup key a label should answer to.

    A syllabus writes "ROS2" where the taxonomy writes "ROS 2", and
    "Sensors" where it writes "sensor". Indexing all three forms lets the
    exact stage catch those without a similarity search.
    """
    norm = normalize(text)
    if not norm:
        return set()

    forms = {norm}
    forms.add(norm.replace(" ", "").replace(".", ""))

    singular = " ".join(_singularize(w) for w in norm.split())
    forms.add(singular)

    meaningful = tokens(norm)
    if meaningful:
        forms.add(" ".join(meaningful))

    return {f for f in forms if len(f) > 1}


# ── Records ────────────────────────────────────────────────────
def make_skill(skill_id: str, label: str, source: str, **fields) -> dict:
    """
    Build one canonical skill record.

    Args:
        skill_id: Namespaced identifier, e.g. "esco:1a2b..." or
            "custom:ros2-node-development". Unique across the taxonomy.
        label: The preferred English label.
        source: One of esco, onet, custom.
        **fields: aliases, description, skill_type, uri, labels, broader.

    Returns:
        The skill dictionary the rest of the pipeline passes around.
    """
    if source not in SOURCE_RANK:
        raise ValueError(f"Unknown taxonomy source: {source}")

    skill_type = fields.get("skill_type") or "skill"
    if skill_type not in VALID_TYPES:
        skill_type = "skill"

    aliases = []
    seen = {normalize(label)}
    for alias in fields.get("aliases") or []:
        norm = normalize(alias)
        if norm and norm not in seen:
            seen.add(norm)
            aliases.append(alias.strip())

    return {
        "id": skill_id,
        "label": label.strip(),
        "source": source,
        "skill_type": skill_type,
        "aliases": aliases,
        "description": (fields.get("description") or "").strip(),
        "uri": fields.get("uri") or "",
        # Preferred labels in other languages, keyed by ISO code. Arabic is
        # the one that matters here; ESCO supplies it, custom skills may not.
        "labels": fields.get("labels") or {},
        # Parent concept labels, used as retrieval context only.
        "broader": fields.get("broader") or [],
    }


def skill_text(skill: dict) -> str:
    """
    The text an embedding model should see for this skill.

    Label first because it carries the most signal, then the aliases that
    a syllabus might actually use, then a trimmed description for the
    domain words that disambiguate homonyms ("Java" the language versus
    the island).
    """
    parts = [skill["label"]]
    parts.extend(skill.get("aliases", []))
    if skill.get("broader"):
        parts.append(" ".join(skill["broader"]))
    description = skill.get("description", "")
    if description:
        parts.append(description[:300])
    return " . ".join(p for p in parts if p)


# ── Merge ──────────────────────────────────────────────────────
def merge_skills(*groups) -> list:
    """
    Combine skills from several sources into one vocabulary.

    Records that normalise to the same label are folded together: the
    highest-ranked source keeps the identifier, and the loser's labels
    become aliases so its wording still resolves. Distinct concepts that
    happen to share a label are rare enough in these sources that fold-by-
    label is the right trade for the alias recall it buys.
    """
    merged = {}
    order = []

    for group in groups:
        for skill in group:
            key = normalize(skill["label"])
            if not key:
                continue

            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(skill)
                order.append(key)
                continue

            keep, drop = existing, skill
            if SOURCE_RANK[skill["source"]] > SOURCE_RANK[existing["source"]]:
                keep, drop = skill, existing
                merged[key] = dict(keep)
                keep = merged[key]

            known = {normalize(keep["label"])}
            known.update(normalize(a) for a in keep["aliases"])
            for alias in [drop["label"], *drop["aliases"]]:
                if normalize(alias) not in known:
                    known.add(normalize(alias))
                    keep["aliases"].append(alias)

            if not keep["description"] and drop["description"]:
                keep["description"] = drop["description"]
            for code, value in drop.get("labels", {}).items():
                keep.setdefault("labels", {}).setdefault(code, value)

    ids = set()
    result = []
    for key in order:
        skill = merged[key]
        # Identifier collisions across sources would silently overwrite a
        # canonical record downstream, so make them loud.
        if skill["id"] in ids:
            raise ValueError(f"Duplicate taxonomy id: {skill['id']}")
        ids.add(skill["id"])
        result.append(skill)
    return result


# ── Alias Index ────────────────────────────────────────────────
class AliasIndex:
    """
    Exact-match lookup over every label and alias in the taxonomy.

    This is the first stage of matching and the cheapest.  It also records
    provenance and collisions so the matcher can distinguish an authoritative
    preferred label from an ambiguous generic alias.
    """

    def __init__(self, skills: list):
        self._by_key = {}
        self._entries_by_key = {}
        self._by_id = {}
        order = 0
        for skill in skills:
            self._by_id[skill["id"]] = skill
            surfaces = [("label", skill["label"])]
            surfaces.extend(("alias", alias) for alias in skill.get("aliases", []))
            surfaces.extend(
                ("translated_label", label)
                for label in skill.get("labels", {}).values()
            )
            for kind, surface in surfaces:
                entry = {
                    "skill": skill,
                    "surface": surface,
                    "kind": kind,
                    "order": order,
                }
                order += 1
                for key in key_forms(surface):
                    # First writer wins: sources are merged in rank order,
                    # so an ESCO alias is not displaced by a custom one.
                    self._by_key.setdefault(key, skill)
                    self._entries_by_key.setdefault(key, []).append(entry)

    def __len__(self) -> int:
        return len(self._by_id)

    def lookup(self, term: str):
        """Return the skill an exact term resolves to, or None."""
        for key in key_forms(term):
            skill = self._by_key.get(key)
            if skill is not None:
                return skill
        return None

    def lookup_details(self, term: str):
        """Return exact-match provenance and collisions for policy decisions.

        ``lookup`` remains the small backwards-compatible API.  The matcher
        needs more information: a preferred label is safer than a generic
        alias, and an alias claimed by several skills must not be accepted
        just because its first index entry won.
        """
        matches = []
        seen = set()
        for key in key_forms(term):
            for entry in self._entries_by_key.get(key, []):
                identity = (
                    entry["skill"]["id"], entry["kind"], normalize(entry["surface"]),
                )
                if identity not in seen:
                    seen.add(identity)
                    matches.append(entry)
        if not matches:
            return None

        term_norm = normalize(term)
        kind_rank = {"label": 0, "translated_label": 1, "alias": 2}

        def priority(entry):
            # An exact preferred label outranks an alias collision.  Exact
            # surface spellings then outrank matches found only through a
            # compact, singular, or stopword-dropped key form.
            surface_exact = normalize(entry["surface"]) == term_norm
            return (
                0 if surface_exact else 1,
                kind_rank[entry["kind"]],
                entry["order"],
            )

        chosen = min(matches, key=priority)
        matched_skills = {}
        for entry in sorted(matches, key=lambda item: item["order"]):
            matched_skills.setdefault(entry["skill"]["id"], entry["skill"])
        return {
            "skill": chosen["skill"],
            "matched_skills": list(matched_skills.values()),
            "matched_surface": chosen["surface"],
            "matched_kind": chosen["kind"],
            "surface_exact": normalize(chosen["surface"]) == term_norm,
            "unique": len(matched_skills) == 1,
            "collision_count": len(matched_skills),
        }

    def get(self, skill_id: str):
        """Return a skill by canonical id, or None."""
        return self._by_id.get(skill_id)


class Taxonomy:
    """A loaded vocabulary: the skills, their alias index, and a fingerprint."""

    def __init__(self, skills: list, version: str = TAXONOMY_VERSION):
        self.skills = skills
        self.version = version
        self.index = AliasIndex(skills)

    def __len__(self) -> int:
        return len(self.skills)

    @property
    def fingerprint(self) -> str:
        """
        Content hash of the vocabulary.

        Stored alongside the vector index so a taxonomy that has changed
        since the embeddings were built is detected instead of silently
        returning matches against stale vectors.
        """
        digest = hashlib.sha256()
        digest.update(self.version.encode("utf-8"))
        for skill in self.skills:
            digest.update(skill["id"].encode("utf-8"))
            digest.update(skill_text(skill).encode("utf-8"))
        return digest.hexdigest()[:16]

    def counts(self) -> dict:
        """Skill count per source, for reporting."""
        counts = {}
        for skill in self.skills:
            counts[skill["source"]] = counts.get(skill["source"], 0) + 1
        return counts


# ── Persistence ────────────────────────────────────────────────
def save_taxonomy(skills: list, path=MERGED_PATH) -> None:
    """Write the merged taxonomy as JSON Lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for skill in skills:
            f.write(json.dumps(skill, ensure_ascii=False) + "\n")


def read_jsonl(path) -> list:
    """Read a JSON Lines file, tolerating blank lines."""
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_custom_skills(path=CUSTOM_SKILLS_PATH) -> list:
    """Load the hand-curated technology skills."""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    skills = []
    for entry in payload.get("skills", []):
        skills.append(make_skill(
            skill_id=f"custom:{entry['id']}",
            label=entry["label"],
            source="custom",
            aliases=entry.get("aliases"),
            description=entry.get("description"),
            skill_type=entry.get("type"),
            labels=entry.get("labels"),
            broader=entry.get("broader"),
        ))
    return skills


def load_taxonomy(path=MERGED_PATH, fallback_to_custom: bool = True) -> Taxonomy:
    """
    Load the vocabulary the matcher should use.

    Prefers the merged file produced by run_taxonomy_build; falls back to
    the curated custom skills so the pipeline still runs before anyone has
    downloaded ESCO or O*NET.
    """
    path = Path(path)
    skills = read_jsonl(path)

    # The merged file is a build artifact. Editing custom_skills.json and
    # forgetting to rebuild is an easy mistake to make and a silent one to
    # live with: matching would keep using the previous vocabulary.
    if skills and CUSTOM_SKILLS_PATH.exists():
        if CUSTOM_SKILLS_PATH.stat().st_mtime > path.stat().st_mtime:
            logging.getLogger("careercompass.taxonomy").warning(
                "%s is newer than %s — run `python -m careercompass.cli.build_taxonomy` "
                "to pick up the change.", CUSTOM_SKILLS_PATH, path
            )

    if not skills and fallback_to_custom:
        skills = load_custom_skills()
    if not skills:
        raise FileNotFoundError(
            f"No taxonomy found at {path} and no custom skills to fall back on. "
            f"Run: python -m careercompass.cli.build_taxonomy"
        )
    return Taxonomy(skills)
