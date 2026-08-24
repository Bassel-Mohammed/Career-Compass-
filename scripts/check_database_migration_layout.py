#!/usr/bin/env python3
"""Dependency-free checks for both services' migration packaging and ordering."""

from __future__ import annotations

import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise AssertionError(message)


def require_nonempty(path: Path) -> None:
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        fail(f"Migration is missing or empty: {path.relative_to(ROOT)}")


def require_contiguous(label: str, versions: list[int], minimum_latest: int) -> None:
    if not versions:
        fail(f"{label} has no migrations")
    if len(versions) != len(set(versions)):
        fail(f"{label} has duplicate versions: {versions}")
    expected = list(range(1, max(versions) + 1))
    if sorted(versions) != expected:
        fail(f"{label} must be contiguous from 1: found {sorted(versions)}")
    if max(versions) < minimum_latest:
        fail(f"{label} unexpectedly ends at {max(versions)}; expected at least {minimum_latest}")


def backend_layout() -> set[str]:
    sql_dir = ROOT / "backend/src/main/resources/db/migration"
    java_dir = ROOT / "backend/src/main/java/db/migration"
    version_pattern = re.compile(r"^V(?P<version>[0-9]+)__[A-Za-z0-9_]+\.(?:sql|java)$")
    files = sorted(sql_dir.glob("V*__*.sql")) + sorted(java_dir.glob("V*__*.java"))
    versions: list[int] = []
    for path in files:
        require_nonempty(path)
        match = version_pattern.fullmatch(path.name)
        if match is None:
            fail(f"Invalid backend migration filename: {path.relative_to(ROOT)}")
        versions.append(int(match.group("version")))
    require_contiguous("Backend Flyway chain", versions, minimum_latest=4)

    baseline = sql_dir / "V1__baseline.sql"
    require_nonempty(baseline)

    application = (ROOT / "backend/src/main/resources/application.yml").read_text(
        encoding="utf-8"
    )
    for setting in ("locations: classpath:db/migration", "baseline-on-migrate: false"):
        if setting not in application:
            fail(f"Backend Flyway setting is missing: {setting}")

    pom_root = ET.parse(ROOT / "backend/pom.xml").getroot()
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    artifacts = {
        element.text
        for element in pom_root.findall(".//m:dependency/m:artifactId", namespace)
    }
    for dependency in ("flyway-core", "flyway-mysql"):
        if dependency not in artifacts:
            fail(f"Backend dependency is missing: {dependency}")

    return created_tables(baseline.read_text(encoding="utf-8"))


def ai_layout() -> set[str]:
    migration_dir = ROOT / "ai-service/src/careercompass/db/migrations"
    version_pattern = re.compile(r"^(?P<version>[0-9]{3})_[a-z0-9_]+\.sql$")
    files = sorted(migration_dir.glob("*.sql"))
    versions: list[int] = []
    combined_sql = []
    for path in files:
        require_nonempty(path)
        match = version_pattern.fullmatch(path.name)
        if match is None:
            fail(f"Invalid AI migration filename: {path.relative_to(ROOT)}")
        versions.append(int(match.group("version")))
        combined_sql.append(path.read_text(encoding="utf-8"))
    require_contiguous("AI PostgreSQL chain", versions, minimum_latest=5)

    require_nonempty(migration_dir / "__init__.py")
    pyproject = tomllib.loads((ROOT / "ai-service/pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject.get("tool", {}).get("setuptools", {}).get("package-data", {})
    if "*.sql" not in package_data.get("careercompass.db.migrations", []):
        fail("AI SQL migrations are not declared as Python package data")
    scripts = pyproject.get("project", {}).get("scripts", {})
    if scripts.get("cc-db-migrate") != "careercompass.db.migrate:main":
        fail("AI migration CLI entry point is missing")

    return created_tables("\n".join(combined_sql))


def created_tables(sql: str) -> set[str]:
    return {
        match.group(1).lower()
        for match in re.finditer(
            r"(?im)^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([a-z0-9_]+)",
            sql,
        )
    }


def main() -> None:
    backend_tables = backend_layout()
    ai_tables = ai_layout()

    # This overlap is intentional but dangerous: the two job_skills tables have
    # incompatible shapes and are safe only because MySQL and PostgreSQL remain
    # separate service-owned databases. Any additional overlap needs review.
    overlap = backend_tables & ai_tables
    if overlap != {"job_skills"}:
        fail(f"Unexpected cross-service table-name overlap: {sorted(overlap)}")

    print("Database migration layout valid: backend Flyway and AI PostgreSQL chains are separate.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"database migration layout error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
