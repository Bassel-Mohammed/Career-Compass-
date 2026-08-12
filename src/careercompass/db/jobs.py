"""
CareerCompass — Job Storage (PostgreSQL)

Reads and writes the scraped LinkedIn postings.

Schema lives in careercompass/db/migrations/001_linkedin_jobs.sql.
Connection handling is in careercompass.db.connection.

Usage:
    from careercompass.db.jobs import init_job_tables, insert_jobs
"""

import logging

import psycopg2

from careercompass.db.connection import get_connection, run_migration

logger = logging.getLogger("careercompass.jobs")


def init_job_tables() -> None:
    """Create the job tables if they do not exist."""
    run_migration("001_linkedin_jobs.sql")


def get_existing_urls(conn) -> set:
    """Return a set of all LinkedIn job URLs already in the database."""
    with conn.cursor() as cur:
        cur.execute("SELECT url FROM linkedin_jobs")
        return {row[0] for row in cur.fetchall()}


def insert_jobs(conn, jobs: list[dict]) -> int:
    """
    Insert a batch of jobs into linkedin_jobs.
    Uses ON CONFLICT (url) DO NOTHING to skip duplicates.
    Returns the number of newly inserted rows.
    """
    if not jobs:
        return 0

    sql = """
        INSERT INTO linkedin_jobs (
            career_path, search_query, title, company_name,
            location, url, description, seniority_level,
            employment_type, job_function, industries,
            posted_date, is_relevant
        ) VALUES (
            %(career_path)s, %(search_query)s, %(title)s, %(company_name)s,
            %(location)s, %(url)s, %(description)s, %(seniority_level)s,
            %(employment_type)s, %(job_function)s, %(industries)s,
            %(posted_date)s, %(is_relevant)s
        )
        ON CONFLICT (url) DO NOTHING
    """

    inserted = 0
    with conn.cursor() as cur:
        for job in jobs:
            cur.execute(sql, job)
            inserted += cur.rowcount

    conn.commit()
    logger.info("Inserted %d new jobs (skipped %d duplicates).", inserted, len(jobs) - inserted)
    return inserted


def get_job_count_by_career_path(conn) -> dict:
    """Return a dict of {career_path: count} for reporting."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT career_path, COUNT(*) FROM linkedin_jobs "
            "WHERE is_relevant = TRUE GROUP BY career_path ORDER BY career_path"
        )
        return dict(cur.fetchall())


def get_total_count(conn) -> int:
    """Return total number of jobs in the database."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM linkedin_jobs")
        return cur.fetchone()[0]
