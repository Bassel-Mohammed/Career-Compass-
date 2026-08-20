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


# ── Job skills ─────────────────────────────────────────────────
JOB_MIGRATION = "003_job_skills.sql"


def init_job_skill_tables(conn=None) -> None:
    """Create the job-skill and ontology tables if they do not exist."""
    run_migration(JOB_MIGRATION, conn=conn)


def store_job_skills(job_id: int, skills: list, conn=None) -> int:
    """
    Upsert one posting's matched skills.

    Terms that did not resolve are stored with a NULL skill_id, exactly as
    store_course_skills does — the two sides of the join should record
    their gaps the same way.

    Args:
        job_id: The linkedin_jobs row these skills came from.
        skills: Extracted skills carrying a "match" record.

    Returns:
        Number of rows written.
    """
    if not job_id:
        raise ValueError("job_id is required to store job skills")

    owned = conn is None
    conn = conn or get_connection()

    rows = []
    for skill in skills:
        match = skill.get("match") or {}
        rows.append((
            job_id,
            skill["term"],
            "+".join(skill.get("sources", [])),
            skill["level"],
            skill["weight"],
            match.get("canonical_id"),
            match.get("match_method"),
            match.get("match_score"),
            match.get("review_status", "no_match"),
            match.get("taxonomy_version", TAXONOMY_VERSION),
        ))

    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO job_skills (
                    job_id, term, sources, level, weight,
                    skill_id, match_method, match_score, review_status,
                    taxonomy_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id, term) DO UPDATE SET
                    sources = EXCLUDED.sources,
                    level = EXCLUDED.level,
                    weight = EXCLUDED.weight,
                    skill_id = EXCLUDED.skill_id,
                    match_method = EXCLUDED.match_method,
                    match_score = EXCLUDED.match_score,
                    review_status = EXCLUDED.review_status,
                    taxonomy_version = EXCLUDED.taxonomy_version
            """, rows, page_size=500)
        conn.commit()
        return len(rows)
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()


def store_career_path_skills(rows: list, totals: dict, conn=None) -> int:
    """
    Replace the derived ontology for every path the rows cover.

    Deletes a path's existing rows before inserting, rather than
    upserting: a re-derivation that no longer finds a skill must remove
    it, and an upsert would leave the stale requirement in place forever.

    Args:
        rows: Output of ontology.build_ontology.
        totals: Postings per career path, for the sample_size column.

    Returns:
        Number of rows written.
    """
    if not rows:
        return 0

    owned = conn is None
    conn = conn or get_connection()

    paths = sorted({row["career_path"] for row in rows})
    values = [
        (
            row["career_path"], row["skill_id"], row["posting_count"],
            totals.get(row["career_path"], 0), row["coverage"],
            row["required_score"], row["required_level"], TAXONOMY_VERSION,
        )
        for row in rows
    ]

    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM career_path_skills WHERE career_path = ANY(%s)",
                (paths,),
            )
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO career_path_skills (
                    career_path, skill_id, posting_count, sample_size,
                    coverage, required_score, required_level, taxonomy_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, values, page_size=500)
        conn.commit()
        logger.info("stored %d ontology rows across %d career paths",
                    len(values), len(paths))
        return len(values)
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()


def get_career_path_skills(career_path: str, conn=None) -> list:
    """
    Read one path's required skills, strongest requirement first.

    This is the query the skill-gap module runs: the right-hand side of
    every comparison a student's skill vector is measured against.
    """
    owned = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.skill_id, t.label AS skill_label, c.posting_count,
                       c.sample_size, c.coverage, c.required_score,
                       c.required_level, c.taxonomy_version
                FROM career_path_skills c
                JOIN taxonomy_skills t ON t.skill_id = c.skill_id
                WHERE c.career_path = %s
                ORDER BY c.required_score DESC
            """, (career_path,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        if owned:
            conn.close()


# ── Taxonomy maintenance ───────────────────────────────────────
def remap_retired_skills(taxonomy, conn=None) -> dict:
    """
    Repoint stored matches at the ids a taxonomy rebuild kept.

    Merging two records for one skill retires the loser's id, but rows
    already written still carry it. Left alone the two sides of the join
    drift apart silently: a course matched to `custom:java` and a posting
    matched to `esco:19a8293b…` describe the same skill and compare as
    different ones, so the gap analysis reports a student lacks something
    they were taught.

    The successor is found by resolving the retired label through the
    current alias index — the merge keeps the loser's label as an alias
    precisely so this lookup works. A retired skill whose label no longer
    resolves is left in place rather than guessed at, and reported.

    Returns:
        `{"remapped": {old_id: new_id}, "deleted": [ids], "orphaned": [ids]}`
    """
    owned = conn is None
    conn = conn or get_connection()
    current = {skill["id"] for skill in taxonomy.skills}

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT skill_id, label FROM taxonomy_skills")
            retired = [(sid, label) for sid, label in cur.fetchall()
                       if sid not in current]

            remapped = {}
            orphaned = []
            for skill_id, label in retired:
                details = taxonomy.index.lookup_details(label)
                successor = details["skill"]["id"] if details else None
                if successor and successor != skill_id:
                    remapped[skill_id] = successor
                else:
                    orphaned.append(skill_id)

            for table in ("course_skills", "job_skills"):
                for old_id, new_id in remapped.items():
                    cur.execute(
                        f"UPDATE {table} SET skill_id = %s WHERE skill_id = %s",
                        (new_id, old_id),
                    )

            deletable = list(remapped)
            if deletable:
                cur.execute(
                    "DELETE FROM taxonomy_skills WHERE skill_id = ANY(%s)",
                    (deletable,),
                )
        conn.commit()
        logger.info("remapped %d retired skills, %d could not be resolved",
                    len(remapped), len(orphaned))
        return {"remapped": remapped, "deleted": deletable, "orphaned": orphaned}
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()
