"""
CareerCompass — Database Connection

One place that knows how to reach PostgreSQL and how to apply a
migration. Both the jobs side and the skills side use it, which is the
reason it exists: the skills pipeline used to import its connection from
inside the scraper package, so the two were coupled through a module
neither of them owned.

Usage:
    from careercompass.db.connection import get_connection, run_migration
"""

import logging

import psycopg2

from careercompass.config import DB_CONFIG, MIGRATIONS_DIR

logger = logging.getLogger("careercompass.db")


def get_connection():
    """Create and return a new PostgreSQL connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except psycopg2.Error as exc:
        logger.error("Failed to connect to PostgreSQL: %s", exc)
        raise


def run_migration(filename: str, conn=None) -> None:
    """
    Apply one SQL migration by filename.

    Every migration is written with IF NOT EXISTS, so this is safe to
    call on each start-up.

    Args:
        filename: A file in careercompass/db/migrations, e.g.
            "002_course_skills.sql".
        conn: An existing connection to reuse; one is opened and closed
            here when omitted.
    """
    path = MIGRATIONS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Migration not found: {path}")

    sql = path.read_text(encoding="utf-8")

    owned = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("Applied migration %s", filename)
    except psycopg2.Error:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()
