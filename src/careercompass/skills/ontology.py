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
                   min_coverage: float = MIN_COVERAGE) -> list:
    """
    Aggregate matched job terms into per-path skill requirements.

    Args:
        skills: Output of job_corpus.to_skills, carrying postings_by_path.
        matches: Output of job_matching.match_terms.
        totals: Postings per career path, from path_totals.
        min_coverage: Fraction of a path's postings a skill must reach.

    Returns:
        Rows of `career_path`, `skill_id`, `skill_label`, `posting_count`,
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
                "postings": set(),
                "levels": Counter(),
                "terms": [],
            })
            bucket["postings"].update(count)
            bucket["levels"][skill["level"]] += len(count)
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
            "posting_count": min(matched, total),
            "coverage": round(coverage, 4),
            "required_score": round(coverage * 100, 1),
            "required_level": _dominant_level(bucket["levels"]),
            "terms": sorted(set(bucket["terms"])),
        })

    rows.sort(key=lambda r: (r["career_path"], -r["required_score"]))
    return rows


def _dominant_level(levels: Counter) -> str:
    """The level most of a skill's mentions asked for, deeper on a tie."""
    if not levels:
        return "intermediate"
    return max(levels.items(), key=lambda item: (item[1], LEVEL_RANK[item[0]]))[0]


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
