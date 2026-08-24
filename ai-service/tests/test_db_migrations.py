"""Unit tests for ordered PostgreSQL migration management.

The fake connection models transaction commit/rollback and migration history;
it never opens a socket or reads the developer's configured database.
"""

import pytest

from careercompass.db import connection as db


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.rows)

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params))
        compact = " ".join(sql.split())

        if compact.startswith("SELECT version, filename, checksum"):
            self.rows = list(self.conn.history)
            return

        if compact.startswith(f"INSERT INTO {db.HISTORY_TABLE}"):
            version, filename, checksum = params
            if version == self.conn.fail_version:
                raise RuntimeError(f"simulated failure at {version}")
            self.conn.pending_history.append((version, filename, checksum))
            return

        migration = self.conn.by_sql.get(sql)
        if migration is not None:
            self.conn.executed_versions.append(migration.version)


class FakeConnection:
    def __init__(self, history=(), fail_version=None):
        migrations = db.discover_migrations()
        self.by_sql = {migration.sql: migration for migration in migrations}
        self.history = list(history)
        self.pending_history = []
        self.executed_versions = []
        self.statements = []
        self.fail_version = fail_version
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.history.extend(self.pending_history)
        self.pending_history.clear()
        self.commits += 1

    def rollback(self):
        self.pending_history.clear()
        self.executed_versions.clear()
        self.rollbacks += 1

    def close(self):
        self.closed = True


def history_rows(count=5):
    return [
        (migration.version, migration.filename, migration.checksum)
        for migration in db.discover_migrations()[:count]
    ]


def test_packaged_migrations_are_complete_and_ordered():
    migrations = db.discover_migrations()

    assert [migration.version for migration in migrations] == [1, 2, 3, 4, 5]
    assert migrations[0].filename == "001_linkedin_jobs.sql"
    assert migrations[-1].filename == "005_course_catalog.sql"
    assert all(len(migration.checksum) == 64 for migration in migrations)
    assert all("CREATE" in migration.sql or "ALTER" in migration.sql for migration in migrations)


def test_fresh_database_applies_everything_in_one_transaction():
    conn = FakeConnection()

    applied = db.apply_migrations(conn)

    assert [migration.version for migration in applied] == [1, 2, 3, 4, 5]
    assert conn.executed_versions == [1, 2, 3, 4, 5]
    assert conn.history == history_rows()
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert not conn.closed  # caller-owned connections stay open
    first_sql, first_params = conn.statements[0]
    assert "pg_advisory_xact_lock" in first_sql
    assert first_params == (db.MIGRATION_LOCK_ID,)


def test_repeat_run_is_idempotent_and_executes_no_migration_sql():
    conn = FakeConnection(history_rows())

    assert db.apply_migrations(conn) == []

    assert conn.executed_versions == []
    assert conn.history == history_rows()
    assert conn.commits == 1


def test_upgrade_applies_only_the_pending_suffix():
    conn = FakeConnection(history_rows(3))

    applied = db.apply_migrations(conn)

    assert [migration.version for migration in applied] == [4, 5]
    assert conn.executed_versions == [4, 5]
    assert conn.history == history_rows()


def test_checksum_drift_fails_before_running_sql_and_rolls_back():
    history = history_rows(2)
    history[1] = (history[1][0], history[1][1], "0" * 64)
    conn = FakeConnection(history)

    with pytest.raises(db.MigrationDriftError, match="checksum differs"):
        db.apply_migrations(conn)

    assert conn.executed_versions == []
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_history_gap_is_rejected_instead_of_backfilling_out_of_order():
    second = history_rows(2)[1]
    conn = FakeConnection([second])

    with pytest.raises(db.MigrationDriftError, match="contiguous prefix"):
        db.apply_migrations(conn)

    assert conn.executed_versions == []
    assert conn.rollbacks == 1


def test_failed_migration_rolls_back_schema_and_history_together():
    conn = FakeConnection(fail_version=3)

    with pytest.raises(RuntimeError, match="simulated failure"):
        db.apply_migrations(conn)

    assert conn.history == []
    assert conn.executed_versions == []
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_owned_connection_is_closed(monkeypatch):
    conn = FakeConnection(history_rows())
    monkeypatch.setattr(db, "get_connection", lambda: conn)

    db.apply_migrations()

    assert conn.closed


@pytest.mark.parametrize("value", [None, "", "0", "false", "NO", "off"])
def test_startup_migration_requires_explicit_opt_in(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("CC_DB_AUTO_MIGRATE", raising=False)
    else:
        monkeypatch.setenv("CC_DB_AUTO_MIGRATE", value)

    assert db.auto_migrate_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_startup_migration_accepts_explicit_opt_in(monkeypatch, value):
    monkeypatch.setenv("CC_DB_AUTO_MIGRATE", value)

    assert db.auto_migrate_enabled() is True


def test_invalid_startup_migration_setting_fails_loudly(monkeypatch):
    monkeypatch.setenv("CC_DB_AUTO_MIGRATE", "sometimes")

    with pytest.raises(db.MigrationError, match="CC_DB_AUTO_MIGRATE"):
        db.auto_migrate_enabled()
