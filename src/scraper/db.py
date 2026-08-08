"""
CareerCompass LinkedIn Scraper — PostgreSQL Database Layer

Handles:
  - Connection management
  - Table creation (runs migration SQL)
  - Inserting scraped jobs (with ON CONFLICT deduplication)
  - Querying existing URLs (for resume capability)
"""

import logging
import os

import psycopg2
import psycopg2.extras

from src.scraper.config import DB_CONFIG

logger = logging.getLogger("careercompass.scraper")


def get_connection():
    """Create and return a new PostgreSQL connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except psycopg2.Error as e:
        logger.error("Failed to connect to PostgreSQL: %s", e)
        raise


def init_db():
    """
    Run the migration SQL to create tables if they don't exist.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    migration_path = os.path.join(
        os.path.dirname(__file__), "migrations", "001_linkedin_jobs.sql"
    )

    with open(migration_path, "r") as f:
        sql = f.read()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("Database tables initialized successfully.")
    except psycopg2.Error as e:
        conn.rollback()
        logger.error("Failed to initialize database: %s", e)
        raise
    finally:
        conn.close()


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
