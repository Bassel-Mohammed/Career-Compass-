"""
CareerCompass — Taxonomy Ingestion (ESCO, O*NET)

Turns the public skill classifications into the canonical record shape
defined in skill_taxonomy.py.

ESCO is the backbone: ~13.9k skills, stable concept URIs, preferred labels
in 28 languages including Arabic, plus alternative labels — which is what
makes the alias index worth having. It is fetched from the public ESCO API
(no key required) and cached on disk, because a crawl is one request per
concept and nobody should pay for it twice.

O*NET covers the software and tool vocabulary ESCO names only in the
abstract ("use software"), but its distribution is a licence-gated
download, so those readers take a local file rather than fetching.

Usage:
    # One-time, cached crawl of the ICT and engineering branches
    python -m careercompass.cli.build_taxonomy --esco

    from careercompass.skills.sources import load_esco_cache, load_onet
"""

import re
import csv
import json
import time
import logging
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from careercompass.skills.taxonomy import CACHE_DIR, make_skill

logger = logging.getLogger("careercompass.taxonomy")

# ── ESCO ───────────────────────────────────────────────────────

ESCO_API = "https://ec.europa.eu/esco/api"
ESCO_CACHE_PATH = CACHE_DIR / "esco_nodes.jsonl"

# Branches worth crawling for a computing faculty. The full skills pillar
# is four times the size and mostly irrelevant here (nursing, masonry),
# which matters because retrieval precision drops as the candidate pool
# fills with concepts no syllabus will ever mention.
ESCO_DEFAULT_ROOTS = (
    "http://data.europa.eu/esco/isced-f/06",   # information and communication technologies
    "http://data.europa.eu/esco/isced-f/07",   # engineering, manufacturing and construction
    "http://data.europa.eu/esco/isced-f/05",   # natural sciences, mathematics and statistics
    "http://data.europa.eu/esco/skill/S5",     # working with computers
    "http://data.europa.eu/esco/skill/S2",     # information skills
)

# The whole classification, for anyone who wants it.
ESCO_ALL_ROOTS = (
    "http://data.europa.eu/esco/skill/K",      # knowledge
    "http://data.europa.eu/esco/skill/S",      # skills
    "http://data.europa.eu/esco/skill/T",      # transversal skills
)

# A leaf concept carries a UUID; the grouping nodes are coded (S1.2, K06).
ESCO_LEAF_RE = re.compile(
    r"/skill/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Languages to keep off the English record. Arabic is the one CareerCompass
# needs; the other 26 would quadruple the file for no current use.
ESCO_KEEP_LANGUAGES = ("ar",)

USER_AGENT = "CareerCompass/1.0 (academic skill-gap research)"


def _get_json(url: str, timeout: int = 30) -> dict:
    """Fetch and decode one JSON document."""
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _esco_url(uri: str) -> str:
    """Resource URL for a concept, picking the endpoint its kind needs."""
    endpoint = "skill" if ESCO_LEAF_RE.search(uri) else "concept"
    return f"{ESCO_API}/resource/{endpoint}?uri={quote(uri, safe='')}&language=en"


def _children(node: dict) -> list:
    """Child URIs of a node, across both link names ESCO uses."""
    links = node.get("_links", {})
    child_uris = []
    for name in ("narrowerConcept", "narrowerSkill"):
        for child in links.get(name, []) or []:
            uri = child.get("uri")
            if uri:
                child_uris.append(uri)
    return child_uris


def crawl_esco(roots=ESCO_DEFAULT_ROOTS, limit: int = 0, delay: float = 0.2,
               cache_path=ESCO_CACHE_PATH, resume: bool = True) -> int:
    """
    Walk the ESCO hierarchy and cache every concept it reaches.

    One HTTP request per concept, so this is slow and deliberately
    resumable: already-cached URIs are skipped and the cache is appended
    to as it goes, which means an interrupted crawl loses nothing.

    Args:
        roots: Concept URIs to start from.
        limit: Stop after this many newly fetched concepts (0 = no limit).
        delay: Seconds to wait between requests.
        cache_path: JSONL file the raw nodes are appended to.
        resume: Skip URIs already present in the cache.

    Returns:
        Number of concepts newly fetched.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    seen = set()
    frontier = []
    if resume and cache_path.exists():
        # Rebuild both halves of the crawl state: which concepts are done,
        # and which of their children never got fetched. Restoring only
        # the first would leave the roots marked done and the queue empty,
        # so a resumed crawl would have nothing to walk.
        cached = []
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    node = json.loads(line)
                    cached.append(node)
                    seen.add(node["uri"])
        for node in cached:
            frontier.extend(child for child in _children(node) if child not in seen)
        logger.info("Resuming ESCO crawl: %d cached, %d still queued",
                    len(seen), len(set(frontier)))

    queue = []
    queued = set()
    for uri in list(roots) + frontier:
        if uri not in seen and uri not in queued:
            queued.add(uri)
            queue.append(uri)

    fetched = 0
    failed = 0

    with open(cache_path, "a", encoding="utf-8") as cache:
        while queue:
            if limit and fetched >= limit:
                logger.info("Reached limit of %d concepts", limit)
                break

            uri = queue.pop(0)
            if uri in seen:
                # Still needs expanding if it is a group, but a cached
                # group's children are already in the cache too.
                continue

            try:
                node = _get_json(_esco_url(uri))
            except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
                failed += 1
                logger.warning("ESCO fetch failed for %s: %s", uri, exc)
                if failed > 25:
                    raise RuntimeError("Too many ESCO fetch failures; stopping") from exc
                time.sleep(delay * 5)
                continue

            node["uri"] = uri
            cache.write(json.dumps(node, ensure_ascii=False) + "\n")
            cache.flush()
            seen.add(uri)
            fetched += 1

            for child in _children(node):
                if child not in seen and child not in queued:
                    queued.add(child)
                    queue.append(child)

            if fetched % 50 == 0:
                logger.info("Fetched %d concepts (%d queued)", fetched, len(queue))
            time.sleep(delay)

    return fetched


def _literal(value) -> str:
    """
    Pull the text out of an ESCO language-keyed field.

    Descriptions arrive as {"en": {"literal": "...", "mimetype": ...}};
    labels as {"en": "..."} or {"en": ["...", "..."]}.
    """
    if isinstance(value, dict):
        return (value.get("literal") or "").strip()
    if isinstance(value, list):
        return " ".join(str(v) for v in value).strip()
    return str(value or "").strip()


def parse_esco_node(node: dict):
    """Convert one cached ESCO concept into a canonical skill, or None."""
    uri = node.get("uri", "")
    if not ESCO_LEAF_RE.search(uri):
        return None  # grouping node, not a skill

    preferred = node.get("preferredLabel") or {}
    label = _literal(preferred.get("en")) or node.get("title", "")
    if not label:
        return None

    alternatives = (node.get("alternativeLabel") or {}).get("en") or []
    if isinstance(alternatives, str):
        alternatives = [alternatives]

    description = _literal((node.get("description") or {}).get("en"))

    labels = {}
    for code in ESCO_KEEP_LANGUAGES:
        text = _literal(preferred.get(code))
        if text:
            labels[code] = text

    links = node.get("_links", {})
    broader = [
        link.get("title", "")
        for link in (links.get("broaderHierarchyConcept") or [])
        if link.get("title")
    ]

    # ESCO states this outright rather than leaving it to be inferred from
    # the hierarchy: hasSkillType is "knowledge" or "skill/competence".
    skill_type = "skill"
    for link in links.get("hasSkillType") or []:
        if (link.get("title") or "").lower() == "knowledge":
            skill_type = "knowledge"
            break

    # The URI's UUID is the stable public identifier; keep it as the id so
    # a stored match can always be resolved back to data.europa.eu.
    concept_id = uri.rsplit("/", 1)[-1]
    return make_skill(
        skill_id=f"esco:{concept_id}",
        label=label,
        source="esco",
        aliases=[a for a in alternatives if a],
        description=description,
        skill_type=skill_type,
        uri=uri,
        labels=labels,
        broader=broader,
    )


def load_esco_cache(cache_path=ESCO_CACHE_PATH) -> list:
    """Read cached ESCO concepts and return the skills among them."""
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return []

    skills = []
    seen = set()
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            skill = parse_esco_node(json.loads(line))
            # A concept reachable from two branches is cached twice.
            if skill and skill["id"] not in seen:
                seen.add(skill["id"])
                skills.append(skill)
    return skills


def load_esco_csv(path) -> list:
    """
    Read an ESCO CSV export (skills_en.csv) instead of crawling.

    The bulk download from esco.ec.europa.eu is far faster than the API
    when you have it; the columns used here are the ones the standard
    skills export carries.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ESCO CSV not found: {path}")

    skills = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            label = (row.get("preferredLabel") or "").strip()
            uri = (row.get("conceptUri") or "").strip()
            if not label or not uri:
                continue
            # altLabels is a newline-separated list inside one cell.
            aliases = [a.strip() for a in (row.get("altLabels") or "").split("\n") if a.strip()]
            skill_type = "knowledge" if "knowledge" in (row.get("skillType") or "") else "skill"
            skills.append(make_skill(
                skill_id=f"esco:{uri.rsplit('/', 1)[-1]}",
                label=label,
                source="esco",
                aliases=aliases,
                description=(row.get("description") or "").strip(),
                skill_type=skill_type,
                uri=uri,
            ))
    return skills


# ── O*NET ──────────────────────────────────────────────────────

# Element ID prefixes in the Content Model, which is what tells a skill
# apart from a knowledge area without a separate lookup table.
ONET_ELEMENT_TYPES = {
    "1.A": "skill",       # abilities
    "2.A": "skill",       # basic skills
    "2.B": "skill",       # cross-functional skills
    "2.C": "knowledge",   # knowledge areas
}


def _slug(text: str) -> str:
    """Stable identifier fragment for a label."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "unnamed"


def _read_table(path) -> list:
    """Read an O*NET distribution file (tab-separated, sometimes CSV)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"O*NET file not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        return list(csv.DictReader(f, delimiter=delimiter))


def load_onet_technology(path) -> list:
    """
    Read O*NET "Technology Skills.txt".

    Each row ties an occupation to a concrete product ("ROS", "Docker")
    under a commodity heading. The products are the reason to ingest this
    file at all — ESCO has no concept for a named piece of software.
    """
    products = {}
    for row in _read_table(path):
        example = (row.get("Example") or "").strip()
        commodity = (row.get("Commodity Title") or "").strip()
        if not example:
            continue
        entry = products.setdefault(example, {"commodity": commodity, "hot": False})
        if (row.get("Hot Technology") or "").strip().upper() == "Y":
            entry["hot"] = True

    skills = []
    for name, meta in products.items():
        skills.append(make_skill(
            skill_id=f"onet:tech:{_slug(name)}",
            label=name,
            source="onet",
            description=f"Software or technology used in the workplace ({meta['commodity']})."
                        if meta["commodity"] else "Software or technology used in the workplace.",
            skill_type="tool",
            broader=[meta["commodity"]] if meta["commodity"] else [],
        ))
    return skills


def load_onet_content_model(path) -> list:
    """
    Read O*NET "Content Model Reference.txt".

    Supplies the transferable skill and knowledge vocabulary — the layer
    job postings write as "critical thinking" or "systems analysis" — with
    a usable description for each element.
    """
    skills = []
    for row in _read_table(path):
        element_id = (row.get("Element ID") or "").strip()
        name = (row.get("Element Name") or "").strip()
        if not element_id or not name:
            continue

        skill_type = None
        for prefix, mapped in ONET_ELEMENT_TYPES.items():
            if element_id.startswith(prefix):
                skill_type = mapped
                break
        # Only the leaf elements name an actual skill; the parents are
        # headings ("Basic Skills") no posting would ever ask for.
        if skill_type is None or element_id.count(".") < 3:
            continue

        skills.append(make_skill(
            skill_id=f"onet:{element_id}",
            label=name,
            source="onet",
            description=(row.get("Description") or "").strip(),
            skill_type=skill_type,
        ))
    return skills


def load_onet(directory) -> list:
    """
    Load whichever O*NET files are present in a directory.

    Both files are optional so a partial download still contributes.
    """
    directory = Path(directory)
    skills = []

    technology = directory / "Technology Skills.txt"
    if technology.exists():
        skills.extend(load_onet_technology(technology))
    else:
        logger.info("No 'Technology Skills.txt' in %s", directory)

    content_model = directory / "Content Model Reference.txt"
    if content_model.exists():
        skills.extend(load_onet_content_model(content_model))
    else:
        logger.info("No 'Content Model Reference.txt' in %s", directory)

    return skills
