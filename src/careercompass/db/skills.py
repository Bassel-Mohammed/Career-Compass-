"""
CareerCompass — Skill Persistence (PostgreSQL)

Stores the canonical taxonomy and the matched course skills, so the gap
analysis can join a student's completed courses against scraped job
skills through one shared skill_id.

Schema lives in careercompass/db/migrations/002_course_skills.sql.

Usage:
    from careercompass.db import skills as skills_db

    skills_db.init_skill_tables()
    skills_db.store_taxonomy(taxonomy)
    skills_db.store_course_skills("0432405", skills)
"""

import json
import logging

import psycopg2
import psycopg2.extras

from careercompass.db.connection import get_connection, run_migration
from careercompass.skills.taxonomy import TAXONOMY_VERSION, normalize

logger = logging.getLogger("careercompass.skills_db")

MIGRATION = "002_course_skills.sql"


def init_skill_tables(conn=None) -> None:
    """Create the taxonomy and course-skill tables if they do not exist."""
    run_migration(MIGRATION, conn=conn)


# ── Taxonomy ───────────────────────────────────────────────────
def store_taxonomy(taxonomy, conn=None) -> int:
    """
    Upsert every canonical skill and its aliases.

    Returns:
        Number of skills written.
    """
    owned = conn is None
    conn = conn or get_connection()

    skill_rows = [
        (
            skill["id"], skill["label"], skill["source"], skill["skill_type"],
            skill.get("description") or None, skill.get("uri") or None,
            skill.get("labels", {}).get("ar"), taxonomy.version,
        )
        for skill in taxonomy.skills
    ]

    alias_rows = []
    for skill in taxonomy.skills:
        for alias in skill.get("aliases", []):
            alias_rows.append((skill["id"], alias, normalize(alias), "en"))
        for code, label in skill.get("labels", {}).items():
            alias_rows.append((skill["id"], label, normalize(label), code))

    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO taxonomy_skills (
                    skill_id, label, source, skill_type, description, uri,
                    label_ar, taxonomy_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (skill_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    source = EXCLUDED.source,
                    skill_type = EXCLUDED.skill_type,
                    description = EXCLUDED.description,
                    uri = EXCLUDED.uri,
                    label_ar = EXCLUDED.label_ar,
                    taxonomy_version = EXCLUDED.taxonomy_version,
                    updated_at = CURRENT_TIMESTAMP
            """, skill_rows, page_size=500)

            psycopg2.extras.execute_batch(cur, """
                INSERT INTO taxonomy_skill_aliases (
                    skill_id, alias, alias_normalized, language
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (skill_id, alias_normalized) DO NOTHING
            """, alias_rows, page_size=500)
        conn.commit()
        logger.info("Stored %d taxonomy skills and %d aliases",
                    len(skill_rows), len(alias_rows))
        return len(skill_rows)
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()


# ── Course skills ──────────────────────────────────────────────
def store_course_skills(course_code: str, skills: list, conn=None) -> int:
    """
    Upsert a course's matched skills.

    Terms that did not resolve are stored too, with a NULL skill_id: they
    are the review queue, and the record of what the taxonomy is missing.

    Args:
        course_code: The course these skills belong to.
        skills: Extracted skills after SkillMatcher.attach has run.

    Returns:
        Number of rows written.
    """
    if not course_code:
        raise ValueError("course_code is required to store course skills")

    owned = conn is None
    conn = conn or get_connection()

    rows = []
    for skill in skills:
        match = skill.get("match") or {}
        rows.append((
            course_code,
            skill["term"],
            skill["level"],
            skill["weight"],
            skill["evidence_count"],
            "+".join(skill.get("sources", [])),
            json.dumps(skill.get("evidence", []), ensure_ascii=False),
            match.get("canonical_id"),
            match.get("match_method"),
            match.get("match_score"),
            match.get("review_status", "no_match"),
            match.get("reason"),
            json.dumps(match.get("candidates", []), ensure_ascii=False),
            match.get("taxonomy_version", TAXONOMY_VERSION),
        ))

    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO course_skills (
                    course_code, term, level, weight, evidence_count, sources,
                    evidence, skill_id, match_method, match_score,
                    review_status, match_reason, candidates, taxonomy_version
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s,
                    %s::jsonb, %s
                )
                ON CONFLICT (course_code, term) DO UPDATE SET
                    level = EXCLUDED.level,
                    weight = EXCLUDED.weight,
                    evidence_count = EXCLUDED.evidence_count,
                    sources = EXCLUDED.sources,
                    evidence = EXCLUDED.evidence,
                    skill_id = EXCLUDED.skill_id,
                    match_method = EXCLUDED.match_method,
                    match_score = EXCLUDED.match_score,
                    review_status = EXCLUDED.review_status,
                    match_reason = EXCLUDED.match_reason,
                    candidates = EXCLUDED.candidates,
                    taxonomy_version = EXCLUDED.taxonomy_version,
                    matched_at = CURRENT_TIMESTAMP
            """, rows, page_size=200)
        conn.commit()
        return len(rows)
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()


def get_course_skills(course_code: str, accepted_only: bool = True, conn=None) -> list:
    """
    Read a course's skills back.

    Defaults to accepted matches only, and that default is the point: a
    `needs_review` row still carries the skill_id the matcher proposed, so
    a join that forgets to filter on review_status would silently treat an
    unconfirmed guess as fact. Pass accepted_only=False when you are
    building the review UI and want to see the proposals.
    """
    owned = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT term, skill_id, level, weight, review_status, match_method,
                       match_score
                FROM course_skills
                WHERE course_code = %s
                  AND (%s = FALSE OR review_status = 'accepted')
                ORDER BY weight DESC, term
            """, (course_code, accepted_only))
            return [
                {
                    "term": row[0], "skill_id": row[1], "level": row[2],
                    "weight": float(row[3]), "review_status": row[4],
                    "match_method": row[5],
                    "match_score": float(row[6]) if row[6] is not None else None,
                }
                for row in cur.fetchall()
            ]
    finally:
        if owned:
            conn.close()


# ── Review queue ───────────────────────────────────────────────
def get_review_queue(limit: int = 100, conn=None) -> list:
    """Terms a human still needs to decide on, worst-scoring first."""
    owned = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT course_code, term, review_status, match_score, candidates
                FROM course_skills
                WHERE review_status <> 'accepted'
                ORDER BY match_score ASC NULLS FIRST, term
                LIMIT %s
            """, (limit,))
            return [
                {
                    "course_code": row[0], "term": row[1], "review_status": row[2],
                    "match_score": float(row[3]) if row[3] is not None else None,
                    "candidates": row[4] or [],
                }
                for row in cur.fetchall()
            ]
    finally:
        if owned:
            conn.close()


def record_review(term: str, skill_id, decision: str, reviewer: str = "",
                  note: str = "", conn=None) -> None:
    """
    Store one reviewer decision.

    Kept separate from course_skills so re-running the matcher never
    overwrites it, and so the same correction carries across courses.
    `decision` is confirmed, corrected or rejected; a NULL skill_id on a
    rejection means nothing in the taxonomy covers the term.
    """
    if decision not in ("confirmed", "corrected", "rejected"):
        raise ValueError(f"Unknown review decision: {decision}")

    owned = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO skill_match_reviews (
                    term_normalized, skill_id, decision, reviewer, note
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (term_normalized) DO UPDATE SET
                    skill_id = EXCLUDED.skill_id,
                    decision = EXCLUDED.decision,
                    reviewer = EXCLUDED.reviewer,
                    note = EXCLUDED.note,
                    reviewed_at = CURRENT_TIMESTAMP
            """, (normalize(term), skill_id, decision, reviewer or None, note or None))
        conn.commit()
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()


def load_reviewed_matches(conn=None) -> dict:
    """
    Reviewer-confirmed mappings, keyed by normalised term.

    Feeding these back into the matcher is how the review effort compounds
    instead of being repeated every run.
    """
    owned = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT term_normalized, skill_id
                FROM skill_match_reviews
                WHERE decision IN ('confirmed', 'corrected') AND skill_id IS NOT NULL
            """)
            return dict(cur.fetchall())
    finally:
        if owned:
            conn.close()
