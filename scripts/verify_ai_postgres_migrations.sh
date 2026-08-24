#!/usr/bin/env bash

# Verify the Python-owned PostgreSQL migration manager against both an empty
# database and an unmanaged legacy database containing migrations 001-003.
# The caller should point CC_AI_PYTHON at a non-editable wheel installation so
# this also proves that SQL package resources ship with the application.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
AI_DIR="${REPO_ROOT}/ai-service"

CC_PG_HOST="${CC_PG_HOST:-127.0.0.1}"
CC_PG_PORT="${CC_PG_PORT:-5432}"
CC_PG_USER="${CC_PG_USER:-postgres}"
CC_PG_PASSWORD="${CC_PG_PASSWORD:?CC_PG_PASSWORD is required}"
CC_PG_ADMIN_DATABASE="${CC_PG_ADMIN_DATABASE:-postgres}"
CC_PG_DATABASE_PREFIX="${CC_PG_DATABASE_PREFIX:-careercompass_ci_ai}"
CC_AI_PYTHON="${CC_AI_PYTHON:-python}"

# The script drops exactly two disposable databases and rejects application-like
# names. This guard is intentional even in CI, where the PostgreSQL service is
# ephemeral.
if [[ ! "${CC_PG_DATABASE_PREFIX}" =~ ^careercompass_ci_[a-z0-9_]+$ ]]; then
    echo "Refusing unsafe database prefix: ${CC_PG_DATABASE_PREFIX}" >&2
    echo "Use a lowercase prefix beginning with careercompass_ci_." >&2
    exit 2
fi

FRESH_DB="${CC_PG_DATABASE_PREFIX}_fresh"
UPGRADE_DB="${CC_PG_DATABASE_PREFIX}_upgrade"

if ! command -v psql >/dev/null 2>&1; then
    echo "psql client is required" >&2
    exit 1
fi
if [[ ! -x "${CC_AI_PYTHON}" ]] && ! command -v "${CC_AI_PYTHON}" >/dev/null 2>&1; then
    echo "Python interpreter is not executable: ${CC_AI_PYTHON}" >&2
    exit 1
fi

export PGPASSWORD="${CC_PG_PASSWORD}"
PSQL=(
    psql
    --host="${CC_PG_HOST}"
    --port="${CC_PG_PORT}"
    --username="${CC_PG_USER}"
    --no-password
    --set=ON_ERROR_STOP=1
    --tuples-only
    --no-align
)

reset_database() {
    local database="$1"
    "${PSQL[@]}" --dbname="${CC_PG_ADMIN_DATABASE}" \
        --command="DROP DATABASE IF EXISTS \"${database}\" WITH (FORCE);"
    "${PSQL[@]}" --dbname="${CC_PG_ADMIN_DATABASE}" \
        --command="CREATE DATABASE \"${database}\";"
}

query_scalar() {
    local database="$1"
    local query="$2"
    "${PSQL[@]}" --dbname="${database}" --command="${query}" | tr -d '[:space:]'
}

assert_scalar() {
    local database="$1"
    local expected="$2"
    local query="$3"
    local description="$4"
    local actual
    actual="$(query_scalar "${database}" "${query}")"
    if [[ "${actual}" != "${expected}" ]]; then
        echo "${database}: ${description}: expected ${expected}, got ${actual:-<empty>}" >&2
        exit 1
    fi
}

run_packaged_migrations() {
    local database="$1"
    CC_DB_HOST="${CC_PG_HOST}" \
    CC_DB_PORT="${CC_PG_PORT}" \
    CC_DB_NAME="${database}" \
    CC_DB_USER="${CC_PG_USER}" \
    CC_DB_PASSWORD="${CC_PG_PASSWORD}" \
        "${CC_AI_PYTHON}" -m careercompass.db.migrate
}

assert_latest_schema() {
    local database="$1"

    assert_scalar "${database}" "5" \
        "SELECT COUNT(*) FROM careercompass_ai_schema_history;" \
        "complete migration history"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'career_path_skills' AND column_name = 'skill_type' AND data_type = 'character varying';" \
        "career-path skill type"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'catalog_courses';" \
        "course catalog table"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'catalog_course_skills';" \
        "course catalog skill table"
    assert_scalar "${database}" "0" \
        "SELECT COUNT(*) FROM careercompass_ai_schema_history WHERE checksum !~ '^[0-9a-f]{64}$';" \
        "SHA-256 migration checksums"
}

echo "Verifying AI PostgreSQL migrations from an empty database..."
reset_database "${FRESH_DB}"
run_packaged_migrations "${FRESH_DB}"
assert_latest_schema "${FRESH_DB}"
# A second pass must discover zero pending migrations and validate every stored
# checksum against the packaged SQL.
run_packaged_migrations "${FRESH_DB}"
assert_latest_schema "${FRESH_DB}"

echo "Verifying AI PostgreSQL adoption of the unmanaged 001-003 schema..."
reset_database "${UPGRADE_DB}"
for migration in \
    "${AI_DIR}/src/careercompass/db/migrations/001_linkedin_jobs.sql" \
    "${AI_DIR}/src/careercompass/db/migrations/002_course_skills.sql" \
    "${AI_DIR}/src/careercompass/db/migrations/003_job_skills.sql"; do
    "${PSQL[@]}" --dbname="${UPGRADE_DB}" --file="${migration}"
done
run_packaged_migrations "${UPGRADE_DB}"
assert_latest_schema "${UPGRADE_DB}"
run_packaged_migrations "${UPGRADE_DB}"
assert_latest_schema "${UPGRADE_DB}"

echo "AI PostgreSQL migration verification passed (fresh + legacy adoption + repeat)."
