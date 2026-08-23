"""
CareerCompass — Job Corpus Term Pool

Stage between extraction and matching. Mining 2,238 postings yields about
228,000 term mentions; matching each one separately would be absurd, and
matching each *unique* term is still not enough on its own — global dedup
only halves the work, because 79% of unique terms occur exactly once and
are prose fragments no two postings share.

What makes the corpus tractable is document frequency. A term mentioned in
fewer than a handful of postings cannot be a career-path requirement, so
it cannot change the ontology this feeds — dropping it costs nothing and
removes about 95% of the matching work:

    all unique terms        ~91,000
    df >= 3                  ~9,000
    df >= 5                  ~4,700     the default
    df >= 10                 ~1,900

Frequency is counted per posting, never per mention: a posting that says
"Kubernetes" six times wants Kubernetes once, and counting mentions would
let one verbose employer outvote fifty concise ones.

Usage:
    from careercompass.skills.job_corpus import build_term_pool, to_skills

    pool = build_term_pool(jobs)
    skills = to_skills(pool, min_df=5)      # ready for SkillMatcher
"""

import json
import logging
from collections import Counter
from pathlib import Path

from careercompass.config import JOBS_DIR
from careercompass.skills.job_extractor import SOURCE_WEIGHTS, extract_job_skills
from careercompass.skills.phrases import LEVEL_RANK
from careercompass.skills.taxonomy import normalize

logger = logging.getLogger("careercompass.job_corpus")

POOL_PATH = JOBS_DIR / "term_pool.json"

# The matcher reads at most this many evidence lines per term, so pooling
# more only inflates the file.
MAX_EVIDENCE = 3

# Postings a term must appear in before it is worth matching.
DEFAULT_MIN_DF = 5


def _pick_surface(surfaces: Counter) -> str:
    """
    The spelling to show and to match on.

    The most common wins; ties break toward the longer form, which keeps
    "CI/CD" over "ci/cd" and "PostgreSQL" over "postgresql" without
    hard-coding a casing rule.
    """
    best = max(surfaces.items(), key=lambda item: (item[1], len(item[0])))
    return best[0]


def build_term_pool(jobs) -> dict:
    """
    Mine every posting and pool the terms across the whole corpus.

    Args:
        jobs: Iterable of postings — rows of linkedin_jobs, or entries of
            data/clean/all_jobs.json. Each needs `title`, `description`
            and `career_path`.

    Returns:
        `{normalized_term: record}`, where each record carries:
            term              the spelling to match on
            document_frequency  postings mentioning it
            by_career_path    {path: [posting indices]}
            level             the level most postings asked for
            levels            the full distribution behind it
            weight            the best zone weight it was seen in
            sources           every zone it appeared in
            evidence          up to MAX_EVIDENCE lines, best zone first
    """
    pool = {}
    surfaces = {}
    # Evidence is chosen after the whole corpus is seen, so a term's three
    # lines come from its strongest zone rather than from whichever
    # posting happened to be first.
    candidates = {}

    for index, job in enumerate(jobs):
        path = job.get("career_path") or "unknown"
        for skill in extract_job_skills(job):
            key = normalize(skill["term"])
            if not key:
                continue

            record = pool.get(key)
            if record is None:
                record = {
                    "term": skill["term"],
                    "document_frequency": 0,
                    "by_career_path": {},
                    "levels": Counter(),
                    "weight": skill["weight"],
                    "sources": [],
                    "evidence": [],
                }
                pool[key] = record
                surfaces[key] = Counter()
                candidates[key] = []

            record["document_frequency"] += 1
            # Which postings, not how many. Two terms can resolve to one
            # skill ("Prometheus" and "monitoring"), and the ontology has
            # to union their postings rather than add their counts, or
            # one posting is counted once per term that named it.
            record["by_career_path"].setdefault(path, []).append(index)
            surfaces[key][skill["term"]] += 1

            record["levels"][skill["level"]] += 1
            record["weight"] = max(record["weight"], skill["weight"])
            for source in skill["sources"]:
                if source not in record["sources"]:
                    record["sources"].append(source)

            # Keep a bounded shortlist per term rather than every line the
            # corpus ever wrote: a term in 500 postings would otherwise
            # hold 500 strings, and only three are ever read.
            if len(candidates[key]) < MAX_EVIDENCE * 8:
                for item in skill["evidence"]:
                    candidates[key].append(
                        (SOURCE_WEIGHTS.get(item["source"], 0.0), item["text"])
                    )

        if (index + 1) % 500 == 0:
            logger.info("mined %d postings, %d unique terms", index + 1, len(pool))

    for key, record in pool.items():
        record["term"] = _pick_surface(surfaces[key])
        record["level"] = _modal_level(record["levels"])
        record["levels"] = dict(record["levels"])
        record["evidence"] = _pool_evidence(candidates[key])

    return pool


def _modal_level(levels: Counter) -> str:
    """
    The level most postings asked for.

    Deliberately not the maximum. Across 2,238 postings almost every term
    appears in at least one senior listing, so a max saturates to
    "advanced" and stops carrying information. The mode says what the
    market typically wants, which is what a required level means.
    Ties break toward the deeper level, since asking too much of a
    student is the safer error.
    """
    if not levels:
        return "intermediate"
    return max(levels.items(), key=lambda item: (item[1], LEVEL_RANK[item[0]]))[0]


def _pool_evidence(candidates: list) -> list:
    """
    Choose the lines that best explain what a term meant across the corpus.

    Strongest zone first, deduplicated. Pooling beats picking one
    posting's wording: "Java" retrieved alone is ambiguous, and the three
    most authoritative lines any employer wrote about it are a better
    query than the three lines of whichever posting happened to be first.
    """
    seen = set()
    chosen = []
    for _, text in sorted(candidates, key=lambda item: -item[0]):
        cleaned = (text or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        chosen.append(cleaned)
        if len(chosen) >= MAX_EVIDENCE:
            break
    return chosen


def to_skills(pool: dict, min_df: int = DEFAULT_MIN_DF) -> list:
    """
    Shape the pool into the skill records SkillMatcher expects.

    Args:
        pool: Output of build_term_pool.
        min_df: Postings a term must appear in to be matched.

    Returns:
        Skill dictionaries, most widely required first, each carrying the
        same keys the syllabus extractor produces so the matcher needs no
        knowledge of where they came from.
    """
    skills = []
    for key, record in pool.items():
        if record["document_frequency"] < min_df:
            continue
        skills.append({
            "term": record["term"],
            "canonical": None,
            "level": record["level"],
            "weight": record["weight"],
            "evidence_count": record["document_frequency"],
            "sources": record["sources"],
            "evidence": [{"source": "job", "text": text}
                         for text in record["evidence"]],
            # Carried through so the ontology pass can aggregate without
            # re-reading the pool. The posting lists are what let it union
            # across the several terms that resolve to one skill.
            "normalized": key,
            "postings_by_path": record["by_career_path"],
            "by_career_path": {path: len(ids)
                               for path, ids in record["by_career_path"].items()},
        })

    skills.sort(key=lambda s: (-s["evidence_count"], s["term"].lower()))
    return skills


# ── Persistence ────────────────────────────────────────────────
def save_pool(pool: dict, path=POOL_PATH) -> Path:
    """
    Write the whole pool, unfiltered.

    The cutoff is stored alongside rather than applied here, so it can be
    re-tuned without re-mining 2,238 postings.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_terms": len(pool),
        "frequencies": {
            str(threshold): sum(1 for r in pool.values()
                                if r["document_frequency"] >= threshold)
            for threshold in (1, 2, 3, 5, 10, 20)
        },
        "terms": pool,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("wrote %d terms to %s", len(pool), path)
    return path


def load_pool(path=POOL_PATH) -> dict:
    """Read a pool written by save_pool."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["terms"]
