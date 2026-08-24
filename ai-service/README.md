# CareerCompass AI Service

The Python service parses transcripts and syllabi, maintains the canonical
skill vocabulary, calculates skill vectors and gaps, recommends courses,
generates quizzes, and performs matching operations.

## Requirements

- Python 3.10+
- `uv` or `pip`
- PostgreSQL for database-backed features

## Install

```bash
cd ai-service
uv venv .venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

Optional semantic and hosted-LLM dependencies:

```bash
uv pip install -e ".[semantic]"
uv pip install -e ".[llm]"
```

## PostgreSQL schema

The AI knowledge base is PostgreSQL-specific and is separate from the Java
backend's MySQL/H2 application database. Do not apply `backend/db/schema.sql`
to this database: both systems have a table named `job_skills` with different
meanings and incompatible columns.

After configuring `CC_DB_*`, apply or upgrade the complete schema with:

```bash
cc-db-migrate
# equivalent: python -m careercompass.db.migrate
```

The command takes a PostgreSQL advisory lock, validates immutable SHA-256
checksums in `careercompass_ai_schema_history`, and applies every pending
`NNN_*.sql` migration in one transaction. It is safe to repeat. Never edit an
applied migration; add the next numbered file instead.

FastAPI does not mutate a configured database at startup unless an operator
explicitly sets `CC_DB_AUTO_MIGRATE=1`. Prefer the command above as a separate
deployment step after backup and rehearsal.

## Run the API

```bash
cd ai-service
uvicorn careercompass.api.app:app --reload --port 8000
```

## Useful commands

```bash
cc-build-taxonomy
cc-extract-skills "data/syllabi/robotics_programming.pdf" --match
cc-match-skills "data/syllabi/robotics_programming.pdf"
cc-parse-transcript plan.pdf
cc-db-migrate
```

## Test

```bash
cd ai-service
pytest -q
```

Implementation and API notes are in [`docs/`](docs/).
