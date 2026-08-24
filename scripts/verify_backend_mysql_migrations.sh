#!/usr/bin/env bash

# Verify the Java-owned MySQL migration chain in two isolated databases:
#
#   1. fresh:   Flyway migrates an empty database from V1 to the latest version;
#   2. upgrade: the historical V1 schema is loaded without Flyway metadata, then
#               explicitly baselined at V1 before pending migrations run.
#
# Both databases are started twice. Spring Boot's production profile uses
# Hibernate `ddl-auto: validate`, so reaching "Started CareerCompassApplication"
# proves that Flyway's result also matches the JPA model.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"

CC_MYSQL_HOST="${CC_MYSQL_HOST:-127.0.0.1}"
CC_MYSQL_PORT="${CC_MYSQL_PORT:-3306}"
CC_MYSQL_USER="${CC_MYSQL_USER:-root}"
CC_MYSQL_PASSWORD="${CC_MYSQL_PASSWORD:?CC_MYSQL_PASSWORD is required}"
CC_MYSQL_DATABASE_PREFIX="${CC_MYSQL_DATABASE_PREFIX:-careercompass_ci_backend}"
CC_BACKEND_START_TIMEOUT="${CC_BACKEND_START_TIMEOUT:-90}"

# This script drops its two target databases. The prefix guard makes it
# impossible to point it at an ordinary application database accidentally.
if [[ ! "${CC_MYSQL_DATABASE_PREFIX}" =~ ^careercompass_ci_[a-z0-9_]+$ ]]; then
    echo "Refusing unsafe database prefix: ${CC_MYSQL_DATABASE_PREFIX}" >&2
    echo "Use a lowercase prefix beginning with careercompass_ci_." >&2
    exit 2
fi

FRESH_DB="${CC_MYSQL_DATABASE_PREFIX}_fresh"
UPGRADE_DB="${CC_MYSQL_DATABASE_PREFIX}_upgrade"
V1_SCHEMA="${BACKEND_DIR}/src/main/resources/db/migration/V1__baseline.sql"

if [[ ! -s "${V1_SCHEMA}" ]]; then
    echo "Flyway V1 baseline is missing: ${V1_SCHEMA}" >&2
    exit 1
fi

if ! command -v mysql >/dev/null 2>&1; then
    echo "mysql client is required" >&2
    exit 1
fi

BACKEND_JAR="${CC_BACKEND_JAR:-}"
if [[ -z "${BACKEND_JAR}" ]]; then
    BACKEND_JAR="$(find "${BACKEND_DIR}/target" -maxdepth 1 -type f \
        -name 'careercompass-backend-*.jar' ! -name '*.original' -print -quit 2>/dev/null || true)"
fi
if [[ -z "${BACKEND_JAR}" || ! -s "${BACKEND_JAR}" ]]; then
    echo "Backend executable jar not found. Run 'mvn -DskipTests package' first." >&2
    exit 1
fi

export MYSQL_PWD="${CC_MYSQL_PASSWORD}"
MYSQL=(
    mysql
    --protocol=TCP
    --host="${CC_MYSQL_HOST}"
    --port="${CC_MYSQL_PORT}"
    --user="${CC_MYSQL_USER}"
    --batch
    --skip-column-names
)

reset_database() {
    local database="$1"
    "${MYSQL[@]}" -e "DROP DATABASE IF EXISTS \`${database}\`; CREATE DATABASE \`${database}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
}

query_scalar() {
    local database="$1"
    local query="$2"
    "${MYSQL[@]}" "${database}" -e "${query}" | tr -d '[:space:]'
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

start_and_validate() {
    local database="$1"
    local baseline_on_migrate="$2"
    local log_file
    local app_pid

    log_file="$(mktemp "${TMPDIR:-/tmp}/careercompass-backend-db.XXXXXX.log")"

    SPRING_PROFILES_ACTIVE=prod \
    SPRING_FLYWAY_BASELINE_ON_MIGRATE="${baseline_on_migrate}" \
    SPRING_FLYWAY_BASELINE_VERSION=1 \
    DB_URL="jdbc:mysql://${CC_MYSQL_HOST}:${CC_MYSQL_PORT}/${database}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC" \
    DB_USERNAME="${CC_MYSQL_USER}" \
    DB_PASSWORD="${CC_MYSQL_PASSWORD}" \
    JWT_SECRET="careercompass_ci_database_validation_secret_1234567890" \
    AI_SERVICE_BASE_URL="http://127.0.0.1:9" \
    AI_SERVICE_TOKEN="careercompass-ci-service-token" \
    SERVER_PORT=0 \
        java -jar "${BACKEND_JAR}" >"${log_file}" 2>&1 &
    app_pid=$!

    for ((second = 0; second < CC_BACKEND_START_TIMEOUT; second++)); do
        if grep -q "Started CareerCompassApplication" "${log_file}"; then
            kill "${app_pid}" 2>/dev/null || true
            wait "${app_pid}" 2>/dev/null || true
            rm -f "${log_file}"
            return 0
        fi
        if ! kill -0 "${app_pid}" 2>/dev/null; then
            echo "Backend exited before validating ${database}:" >&2
            sed -n '1,240p' "${log_file}" >&2
            rm -f "${log_file}"
            wait "${app_pid}" 2>/dev/null || true
            return 1
        fi
        sleep 1
    done

    echo "Backend did not validate ${database} within ${CC_BACKEND_START_TIMEOUT}s:" >&2
    sed -n '1,240p' "${log_file}" >&2
    kill "${app_pid}" 2>/dev/null || true
    wait "${app_pid}" 2>/dev/null || true
    rm -f "${log_file}"
    return 1
}

assert_latest_schema() {
    local database="$1"

    assert_scalar "${database}" "4" \
        "SELECT COUNT(*) FROM flyway_schema_history WHERE success = 1 AND version IN ('1','2','3','4');" \
        "complete Flyway history"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'quizzes' AND column_name = 'skill_id' AND column_type = 'varchar(120)';" \
        "canonical quiz skill column"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'skills' AND column_name = 'canonical_skill_id' AND column_type = 'varchar(120)';" \
        "canonical local skill identity"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'career_paths' AND column_name = 'career_path_code' AND column_type = 'varchar(120)';" \
        "immutable career-path code"
    assert_scalar "${database}" "1" \
        "SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE() AND table_name = 'quiz_responses' AND constraint_name = 'uq_quiz_response_question' AND constraint_type = 'UNIQUE';" \
        "one response per quiz question"
}

echo "Verifying backend MySQL migrations from an empty database..."
reset_database "${FRESH_DB}"
start_and_validate "${FRESH_DB}" false
assert_latest_schema "${FRESH_DB}"
# A second ordinary start verifies that Flyway validation and Hibernate
# validation are idempotent after the initial migration.
start_and_validate "${FRESH_DB}" false

echo "Verifying backend MySQL upgrade from the hand-managed V1 schema..."
reset_database "${UPGRADE_DB}"
"${MYSQL[@]}" "${UPGRADE_DB}" <"${V1_SCHEMA}"
start_and_validate "${UPGRADE_DB}" true
assert_latest_schema "${UPGRADE_DB}"
assert_scalar "${UPGRADE_DB}" "1" \
    "SELECT COUNT(*) FROM flyway_schema_history WHERE success = 1 AND version = '1' AND type = 'BASELINE';" \
    "operator-reviewed V1 baseline"
# Baseline-on-migrate is deliberately disabled again. Existing production
# databases must never depend on that escape hatch after their one reviewed
# baseline operation.
start_and_validate "${UPGRADE_DB}" false

echo "Backend MySQL migration verification passed (fresh + V1 upgrade + restart)."
