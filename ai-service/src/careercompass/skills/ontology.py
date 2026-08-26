"""
CareerCompass — Career-Path Skill Ontology

The right half of the gap analysis. The course-to-skill map says what a
student knows; this says what a career path demands, derived from what
employers actually asked for rather than from anyone's opinion.

    postings for a path  ->  accepted skill matches  ->  required level

A requirement is a fraction, never a count. The paths are different sizes
— Data Science has 337 postings and AI/ML has 158 — so "mentioned in 90
postings" means something different in each, while "mentioned in 27% of
them" is comparable across all nine. That fraction becomes the required
score on the same 0-100 scale the skill vector uses, so a gap is a
subtraction.

Only confidently matched terms count. A term the matcher sent to review is
not evidence of a requirement, and letting one through would write a guess
into the ontology every downstream module then treats as ground truth.

The required level is the weighted median of what the postings asked for,
never the mode and never the maximum. Both of those saturate to "advanced"
on this corpus — see `_required_level` for the measured numbers.

Usage:
    from careercompass.skills.ontology import build_ontology

    rows = build_ontology(skills, matches, path_totals)
"""

import json
import logging
from collections import Counter
from pathlib import Path

from careercompass.config import JOBS_DIR
from careercompass.skills.matcher import ACCEPTED
from careercompass.skills.phrases import LEVEL_RANK

logger = logging.getLogger("careercompass.ontology")

ONTOLOGY_PATH = JOBS_DIR / "career_path_skills.json"

# A skill this rare in a path is noise rather than a requirement: at 2% of
# 158 postings it is three employers, which is a coincidence, not a market
# signal.
MIN_COVERAGE = 0.02


def path_totals(jobs) -> dict:
    """Count the postings behind each career path — the denominator."""
    return Counter((job.get("career_path") or "unknown") for job in jobs)


def build_ontology(skills: list, matches: dict, totals: dict,
                   min_coverage: float = MIN_COVERAGE,
                   skill_types: dict = None) -> list:
    """
    Aggregate matched job terms into per-path skill requirements.

    Args:
        skills: Output of job_corpus.to_skills, carrying postings_by_path.
        matches: Output of job_matching.match_terms.
        totals: Postings per career path, from path_totals.
        min_coverage: Fraction of a path's postings a skill must reach.
        skill_types: Optional ``{skill_id: skill_type}`` from the taxonomy.
            A match record carries the canonical id and label but not the
            type, so without this every row's skill_type is None and M3
            cannot separate technical requirements from soft ones.

    Returns:
        Rows of `career_path`, `skill_id`, `skill_label`, `skill_type`,
        `posting_count`,
        `coverage`, `required_score`, `required_level`, `terms`, sorted by
        path then by descending score.
    """
    # (path, skill_id) -> accumulator. Two terms can resolve to the same
    # skill, so this is keyed on the resolved id, not on the term.
    buckets = {}

    for skill in skills:
        record = matches.get(skill["normalized"])
        if not record or record["review_status"] != ACCEPTED:
            continue
        skill_id = record.get("canonical_id")
        if not skill_id:
            continue

        for path, count in skill["postings_by_path"].items():
            bucket = buckets.setdefault((path, skill_id), {
                "label": record["canonical_label"],
                # Carried through so M3 can rank technical and soft
                # requirements separately. Soft skills top nearly every path,
                # which is accurate but gives every student the same advice.
                "skill_type": (skill_types or {}).get(skill_id),
                "postings": set(),
                "levels": Counter(),
                "terms": [],
            })
            bucket["postings"].update(count)
            # Spread this path's postings across the level mix the term was actually asked
            # for at, rather than attributing every one of them to the term's modal level.
            # `levels` is corpus-wide while `count` is per-path, so this assumes a term is
            # asked for at similar depth in every path — far weaker than the assumption it
            # replaces, which was that every posting wanted the modal depth.
            mix = skill.get("levels") or {skill["level"]: 1}
            total_mentions = sum(mix.values()) or 1
            for level_name, mentions in mix.items():
                bucket["levels"][level_name] += len(count) * mentions / total_mentions
            bucket["terms"].append(skill["term"])

    rows = []
    for (path, skill_id), bucket in buckets.items():
        total = totals.get(path, 0)
        if not total:
            continue

        # A union of postings, not a sum of term counts. Five terms
        # resolve to "monitoring and observability" — Grafana, Prometheus,
        # logging, monitoring, observability — and a posting naming three
        # of them is one posting. Summing counted it three times and put
        # the skill at 100% of the path, which is the number the gap
        # analysis would then subtract against.
        matched = len(bucket["postings"])
        coverage = min(1.0, matched / total)
        if coverage < min_coverage:
            continue

        rows.append({
            "career_path": path,
            "skill_id": skill_id,
            "skill_label": bucket["label"],
            "skill_type": bucket["skill_type"],
            "posting_count": min(matched, total),
            "coverage": round(coverage, 4),
            "required_score": round(coverage * 100, 1),
            "required_level": _required_level(bucket["levels"]),
            "terms": sorted(set(bucket["terms"])),
        })

    rows.sort(key=lambda r: (r["career_path"], -r["required_score"]))
    return rows


# Shallowest first, so a cumulative walk crosses the halfway mark at the median.
_LEVEL_ORDER = sorted(LEVEL_RANK, key=LEVEL_RANK.get)


def _required_level(levels: Counter) -> str:
    """The depth at least half the postings asking for a skill wanted.

    The weighted median, not the mode and emphatically not the maximum.

    Each of the alternatives fails on this corpus in its own way, and all three failures look
    identical from the outside — a required level that is "advanced" almost everywhere and
    therefore says nothing:

        maximum   almost every term appears in at least one senior listing, so it saturates
                  outright. Rejected when this module was written.
        mode      advanced is the largest single bucket corpus-wide (51% of mentions), so it
                  wins the plurality for nearly every skill even when most postings asked for
                  less. Measured: 82.5% of requirements came out "advanced" against a corpus
                  where only 51% of mentions were.
        median    crosses at the point half the market is satisfied, which is what a
                  requirement means. Measured: 59% advanced, 40% intermediate — close to the
                  corpus itself.

    The median is deliberately unkind to the tail in both directions: a skill wanted at
    beginner depth by a fifth of postings and intermediate by the rest is an intermediate
    requirement, because meeting the fifth would not make a student employable for the rest.
    """
    if not levels:
        return "intermediate"

    half = sum(levels.values()) / 2
    seen = 0.0
    for level_name in _LEVEL_ORDER:
        seen += levels.get(level_name, 0)
        if seen >= half:
            return level_name
    return "intermediate"


def save_ontology(rows: list, totals: dict, path=ONTOLOGY_PATH) -> Path:
    """Write the ontology with the sample sizes it was derived from."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    by_path = Counter(row["career_path"] for row in rows)
    payload = {
        "derived_from": "job_postings",
        "career_paths": {
            name: {"sample_size": totals.get(name, 0), "skills": by_path.get(name, 0)}
            for name in sorted(totals)
        },
        "total_rows": len(rows),
        "skills": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("wrote %d ontology rows to %s", len(rows), path)
    return path


def load_ontology(path=ONTOLOGY_PATH) -> list:
    """Read an ontology written by save_ontology."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["skills"]
