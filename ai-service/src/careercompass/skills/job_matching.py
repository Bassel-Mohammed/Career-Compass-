"""
CareerCompass — Job Term Matching

Runs the pooled corpus terms through SkillMatcher once each, and fans the
result back across the postings that used them.

The fan-out is why the pool exists. Matching is the expensive stage — a
few thousand terms, of which roughly a fifth reach the LLM — while
attaching a resolved id to the 2,238 postings that mentioned it costs
nothing. Matching per posting instead would repeat the same decision about
"Kubernetes" two hundred times and reach a different answer on some of
them.

The run takes hours, so it checkpoints. Every term already in the
checkpoint is skipped on a resume, which also makes the cutoff cheap to
lower later: dropping min_df from 10 to 5 re-matches only the terms the
higher cutoff excluded.

Usage:
    from careercompass.skills.job_matching import match_terms

    matches = match_terms(skills, matcher, checkpoint=Path("matches.json"))
"""

import json
import logging
import time
from pathlib import Path

from careercompass.config import JOBS_DIR
from careercompass.skills.job_extractor import extract_job_skills
from careercompass.skills.matcher import (
    ACCEPTED, UNMATCHED, SkillMatcher, evidence_text,
)
from careercompass.skills.taxonomy import TAXONOMY_VERSION, normalize

logger = logging.getLogger("careercompass.job_matching")

MATCHES_PATH = JOBS_DIR / "term_matches.json"

# Terms between checkpoint writes. Small enough that a crash costs
# minutes, large enough that the file is not rewritten constantly.
CHECKPOINT_EVERY = 50


def load_checkpoint(path=MATCHES_PATH) -> dict:
    """Read the term-to-match map from a previous run, if there is one."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("matches", {})
    except (OSError, ValueError) as exc:
        logger.warning("ignoring unreadable checkpoint %s: %s", path, exc)
        return {}


def save_checkpoint(matches: dict, path=MATCHES_PATH, **extra) -> Path:
    """Write the term-to-match map, replacing any previous one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {"total": len(matches), **extra, "matches": matches}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # Replace atomically: a checkpoint half-written by an interrupted run
    # would lose every term matched before it.
    tmp.replace(path)
    return path


def match_terms(skills: list, matcher: SkillMatcher, checkpoint=MATCHES_PATH,
                resume: bool = True, progress_every: int = 100) -> dict:
    """
    Resolve every pooled term onto the taxonomy.

    Args:
        skills: Output of job_corpus.to_skills.
        matcher: A built SkillMatcher.
        checkpoint: Where to write progress, or None to keep it in memory.
        resume: Skip terms already in the checkpoint.
        progress_every: Terms between log lines.

    Returns:
        `{normalized_term: match record}` for every term matched, including
        any carried over from a previous run.
    """
    matches = load_checkpoint(checkpoint) if (resume and checkpoint) else {}
    pending = [s for s in skills if s["normalized"] not in matches]

    if not pending:
        logger.info("all %d terms already matched", len(skills))
        return matches

    logger.info("matching %d terms (%d already done)",
                len(pending), len(matches))
    started = time.time()

    for position, skill in enumerate(pending, 1):
        record = matcher.match(skill["term"], evidence_text(skill))
        matches[skill["normalized"]] = record

        if checkpoint and position % CHECKPOINT_EVERY == 0:
            save_checkpoint(matches, checkpoint)
        if position % progress_every == 0:
            elapsed = time.time() - started
            rate = position / elapsed
            remaining = (len(pending) - position) / rate if rate else 0
            logger.info("  %d/%d  %.1f terms/s  ~%.0f min left",
                        position, len(pending), rate, remaining / 60)

    if checkpoint:
        save_checkpoint(matches, checkpoint)
    logger.info("matched %d terms in %.1f min",
                len(pending), (time.time() - started) / 60)
    return matches


# The cross-encoder accepts at 0.72; the lexical reranker at 0.62. A run
# that fell back to lexical therefore auto-accepted a band the stricter
# scorer would have questioned, and that band is where the wrong ids are.
STRICT_ACCEPT_SCORE = 0.72

# High enough that no reranker score clears it, which routes every
# rechecked term to the LLM instead. The LLM is markedly better at these
# — "is GitHub Copilot the same skill as Git?" is a judgement, not a
# similarity.
RECHECK_ACCEPT_SCORE = 0.95


def risky_terms(matches: dict, max_score: float = STRICT_ACCEPT_SCORE) -> list:
    """
    Terms the reranker accepted on its own below the strict threshold.

    These are auto-accepted matches that never reached the LLM and that a
    cross-encoder run would have sent for a second opinion. A wrong
    canonical id here is invisible once stored, so they are worth the
    re-decision even though most of them are right.
    """
    return sorted(
        key for key, record in matches.items()
        if record["review_status"] == ACCEPTED
        and record["match_method"] == "embedding_reranker"
        and record["match_score"] < max_score
    )


def recheck_terms(skills: list, matches: dict, matcher: SkillMatcher,
                  keys=None, checkpoint=MATCHES_PATH) -> dict:
    """
    Re-decide the risky band with a matcher that cannot auto-accept.

    Args:
        skills: Output of job_corpus.to_skills.
        matches: Output of match_terms; updated in place.
        matcher: A matcher built with RECHECK_ACCEPT_SCORE, so every
            candidate falls through to the LLM.
        keys: Terms to recheck; defaults to risky_terms(matches).
        checkpoint: Where to write the updated map.

    Returns:
        Counts of what changed: rechecked, overturned, kept.
    """
    keys = set(keys if keys is not None else risky_terms(matches))
    by_key = {s["normalized"]: s for s in skills}
    counts = {"rechecked": 0, "overturned": 0, "kept": 0}

    for position, key in enumerate(sorted(keys), 1):
        skill = by_key.get(key)
        if skill is None:
            continue
        before = matches[key]
        after = matcher.match(skill["term"], evidence_text(skill))
        matches[key] = after
        counts["rechecked"] += 1
        if after.get("canonical_id") != before.get("canonical_id"):
            counts["overturned"] += 1
            logger.info("  overturned %r: %s -> %s", skill["term"],
                        before.get("canonical_label"),
                        after.get("canonical_label") or after["review_status"])
        else:
            counts["kept"] += 1
        if checkpoint and position % CHECKPOINT_EVERY == 0:
            save_checkpoint(matches, checkpoint)

    if checkpoint:
        save_checkpoint(matches, checkpoint)
    return counts


def attach_to_jobs(jobs, matches: dict, store=None) -> dict:
    """
    Fan the term-level decisions back out across the postings.

    Re-mines each posting — seconds for the whole corpus — and attaches
    the decision already made for each of its terms. Nothing is matched
    again here: that is the point of pooling, and re-deciding per posting
    would reach different answers for the same term.

    A term below the frequency cutoff was never matched, so it carries no
    decision. It is still written, with a null id and `no_match`, for the
    same reason course_skills keeps its unresolved terms — the record of
    what the corpus asked for and the taxonomy could not name.

    Args:
        jobs: The postings the pool was built from, each with an `id`.
        matches: Output of match_terms, keyed on the normalised term.
        store: Optional `callable(job_id, skills)` to persist each
            posting, typically db.skills.store_job_skills.

    Returns:
        Counts of what was attached: postings, rows, and accepted rows.
    """
    counts = {"postings": 0, "rows": 0, "accepted": 0}

    for job in jobs:
        job_id = job.get("id")
        skills = extract_job_skills(job)
        if not skills:
            continue

        for skill in skills:
            record = matches.get(normalize(skill["term"]))
            if record is None:
                record = {
                    "canonical_id": None,
                    "canonical_label": None,
                    "match_method": "below_cutoff",
                    "match_score": 0.0,
                    "review_status": UNMATCHED,
                    "taxonomy_version": TAXONOMY_VERSION,
                }
            skill["match"] = record
            skill["canonical"] = (
                {"id": record["canonical_id"], "label": record["canonical_label"]}
                if record["review_status"] == ACCEPTED else None
            )
            counts["rows"] += 1
            if record["review_status"] == ACCEPTED:
                counts["accepted"] += 1

        counts["postings"] += 1
        if store is not None and job_id:
            store(job_id, skills)

    return counts
