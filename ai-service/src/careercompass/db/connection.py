"""
CareerCompass PostgreSQL connection and schema migrations.

Migrations are package resources named ``NNN_description.sql``. They are
always discovered and applied as one ordered chain; callers cannot choose a
single file and accidentally skip one of its prerequisites. PostgreSQL DDL is
transactional, so the schema changes and their history rows commit together.

The history table records the SHA-256 digest of every applied file. Editing an
old migration after it has shipped is therefore a loud error rather than a
silent difference between two databases. A transaction-scoped advisory lock
serialises concurrent application instances during startup or deployment.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from importlib import resources
from typing import Iterable

import psycopg2

from careercompass.config import DB_CONFIG

logger = logging.getLogger("careercompass.db")

MIGRATION_PACKAGE = "careercompass.db.migrations"
MIGRATION_RE = re.compile(r"^(?P<version>[0-9]{3})_(?P<name>[a-z0-9_]+)\.sql$")
HISTORY_TABLE = "careercompass_ai_schema_history"

# Stable signed bigint derived from ``careercompass-ai-schema``. Transaction
# advisory locks are database-local and automatically released on commit or
# rollback, including when the process is terminated mid-migration.
MIGRATION_LOCK_ID = 4850181443054420809


class MigrationError(RuntimeError):
    """The packaged migration chain or the database history is invalid."""


class MigrationDriftError(MigrationError):
    """An applied migration no longer matches the packaged immutable file."""


@dataclass(frozen=True)
class Migration:
    """One immutable, ordered SQL migration."""

    version: int
    filename: str
    name: str
    checksum: str
    sql: str


def get_connection():
    """Create and return a transactional PostgreSQL connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except psycopg2.Error as exc:
        logger.error("Failed to connect to PostgreSQL: %s", exc)
        raise


def database_configured() -> bool:
    """Whether enough connection fields were supplied to opt into PostgreSQL."""
    return all(DB_CONFIG.get(key) for key in ("host", "dbname", "user"))


def auto_migrate_enabled() -> bool:
    """Run startup migrations only after an explicit operator opt-in.

    Merely configuring a database is not permission to mutate it.  Production
    upgrades should normally run ``cc-db-migrate`` as a separate, observable
    deployment step after backup and rehearsal.
    """
    raw = os.getenv("CC_DB_AUTO_MIGRATE", "").strip().lower()
    if raw in ("", "0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    raise MigrationError(
        "CC_DB_AUTO_MIGRATE must be one of 1/true/yes/on or 0/false/no/off"
    )


def discover_migrations() -> tuple[Migration, ...]:
    """Read and validate the complete migration chain from package resources."""
    root = resources.files(MIGRATION_PACKAGE)
    migrations = []

    for entry in root.iterdir():
        if not entry.is_file() or not entry.name.endswith(".sql"):
            continue
        match = MIGRATION_RE.fullmatch(entry.name)
        if match is None:
            raise MigrationError(
                f"Invalid migration filename {entry.name!r}; expected NNN_description.sql"
            )
        raw = entry.read_bytes()
        migrations.append(
            Migration(
                version=int(match.group("version")),
                filename=entry.name,
                name=match.group("name"),
                checksum=hashlib.sha256(raw).hexdigest(),
                sql=raw.decode("utf-8"),
            )
        )

    migrations.sort(key=lambda migration: migration.version)
    if not migrations:
        raise MigrationError(
            f"No SQL migrations were packaged in {MIGRATION_PACKAGE}; "
            "the installation is incomplete"
        )

    versions = [migration.version for migration in migrations]
    expected = list(range(1, len(migrations) + 1))
    if versions != expected:
        raise MigrationError(
            f"Migration versions must be contiguous from 001; found {versions}"
        )
    return tuple(migrations)


def _create_history_table(cur) -> None:
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
            version      INTEGER PRIMARY KEY CHECK (version > 0),
            filename     VARCHAR(255) NOT NULL UNIQUE,
            checksum     CHAR(64) NOT NULL,
            applied_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _load_history(cur) -> list[tuple[int, str, str]]:
    cur.execute(
        f"SELECT version, filename, checksum FROM {HISTORY_TABLE} ORDER BY version"
    )
    return [(int(version), filename, checksum.strip()) for version, filename, checksum in cur]


def _validate_history(
    migrations: tuple[Migration, ...], history: Iterable[tuple[int, str, str]]
) -> int:
    """Validate applied rows and return the number forming the applied prefix."""
    applied = list(history)
    if len(applied) > len(migrations):
        raise MigrationDriftError(
            "Database schema is newer than this application: "
            f"history has {len(applied)} migrations, package has {len(migrations)}"
        )

    for position, (version, filename, checksum) in enumerate(applied):
        expected = migrations[position]
        if version != expected.version:
            raise MigrationDriftError(
                "Migration history is not a contiguous prefix: "
                f"expected version {expected.version:03d}, found {version:03d}"
            )
        if filename != expected.filename:
            raise MigrationDriftError(
                f"Migration {version:03d} filename changed: database has "
                f"{filename!r}, package has {expected.filename!r}"
            )
        if checksum != expected.checksum:
            raise MigrationDriftError(
                f"Migration {filename} checksum differs from the applied version; "
                "create a new migration instead of editing an old one"
            )
    return len(applied)


def apply_migrations(conn=None) -> list[Migration]:
    """
    Apply every pending migration in order and return those newly applied.

    One PostgreSQL transaction covers the advisory lock, all pending DDL, and
    every history insert. A failure leaves both schema and history unchanged.
    When a connection is supplied, this function still owns that transaction:
    it commits on success and rolls back on every failure.
    """
    migrations = discover_migrations()
    owned = conn is None
    conn = conn or get_connection()
    if getattr(conn, "autocommit", False):
        conn.autocommit = False

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
            _create_history_table(cur)
            applied_count = _validate_history(migrations, _load_history(cur))
            pending = list(migrations[applied_count:])

            for migration in pending:
                logger.info("Applying migration %s", migration.filename)
                cur.execute(migration.sql)
                cur.execute(
                    f"""
                    INSERT INTO {HISTORY_TABLE} (version, filename, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.filename, migration.checksum),
                )

        conn.commit()
        if pending:
            logger.info("Applied %d database migration(s)", len(pending))
        else:
            logger.info("Database schema is current at version %03d", migrations[-1].version)
        return pending
    except Exception:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()
