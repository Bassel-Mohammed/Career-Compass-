# Database migration verification

CareerCompass deliberately has two database owners and two engines:

- Spring Boot owns business data in MySQL. Flyway migrations are packaged at
  `backend/src/main/resources/db/migration/`.
- The AI service owns derived taxonomy, catalog, review and extraction data in
  PostgreSQL. Its ordered SQL resources are packaged with the Python wheel.

The schemas must not be combined. In particular, each service has a different
table named `job_skills`; their IDs, columns and ownership are intentionally
unrelated.

## What CI verifies

The `backend-database` job creates two disposable MySQL databases:

1. an empty database migrated from V1 through the latest Flyway version;
2. the historical hand-managed V1 schema, explicitly baselined at version 1,
   then upgraded through the remaining migrations.

It boots the production Spring profile against both results. Production uses
Hibernate schema validation, so a successful start checks the migration chain
against the JPA entities as well as checking Flyway history. Each database is
started a second time with ordinary migration settings to catch non-idempotent
startup behavior.

The `ai-database` job builds and installs the AI wheel, then creates two
disposable PostgreSQL databases:

1. an empty database migrated through every packaged SQL resource;
2. an unmanaged legacy schema containing migrations 001-003, adopted and
   upgraded by the migration manager.

It applies the manager twice and checks its five checksummed history records,
the migration-004 column and the migration-005 catalog tables. Running through
the installed wheel is important: editable source installs can hide missing
package resources.

## Local reproduction

The scripts intentionally refuse database prefixes that do not begin with
`careercompass_ci_`, because they drop and recreate their test databases. Point
them only at disposable MySQL and PostgreSQL instances.

Build the Java executable before running its check:

```bash
cd backend
mvn -B -DskipTests package
cd ..

CC_MYSQL_PASSWORD=local_test_password \
  bash scripts/verify_backend_mysql_migrations.sh
```

Install the Python wheel into an isolated environment before running its check:

```bash
cd ai-service
uv build --wheel --out-dir /tmp/careercompass-ai-wheel
uv venv /tmp/careercompass-ai-db-venv
uv pip install --python /tmp/careercompass-ai-db-venv/bin/python \
  /tmp/careercompass-ai-wheel/careercompass-*.whl
cd ..

CC_AI_PYTHON=/tmp/careercompass-ai-db-venv/bin/python \
CC_PG_PASSWORD=local_test_password \
  bash scripts/verify_ai_postgres_migrations.sh
```

Override `CC_MYSQL_HOST`/`CC_MYSQL_PORT` or `CC_PG_HOST`/`CC_PG_PORT` when the
disposable server is not listening on its standard loopback port.
