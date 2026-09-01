# CareerCompass AI Service

The AI service is CareerCompass's internal FastAPI application. It parses transcripts and
syllabi, maps extracted terms to the canonical skill taxonomy, calculates student skill vectors
and career gaps, ranks courses, generates quizzes, and performs mentor and skill matching.

The Spring Boot backend is the public boundary. Browser clients should not call this service
directly.

## Technology

- Python 3.10+
- FastAPI and Uvicorn
- PostgreSQL for extraction review and publication data
- NumPy/pandas and lexical matching by default
- Optional BGE embeddings and cross-encoder reranking
- Ollama, Anthropic, or Google Gemini for optional LLM stages

## Install

[`uv`](https://docs.astral.sh/uv/) is the recommended environment and dependency manager:

```bash
cd ai-service
uv sync --extra dev
cp .env.example .env
```

For semantic models or the hosted Anthropic client, include the relevant extra:

```bash
uv sync --extra dev --extra semantic
uv sync --extra dev --extra llm
```

An editable pip installation is also supported:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Configuration

The checked-in `.env.example` documents all supported matching and database settings. Important
variables include:

| Variable | Purpose | Typical local value |
|---|---|---|
| `CC_DATA_DIR` | Taxonomy, extracted course, and runtime artifact directory | `./data` |
| `CC_SERVICE_TOKEN` | Bearer token required from the Spring backend | local shared token |
| `CC_DB_HOST`, `CC_DB_PORT` | PostgreSQL connection | `localhost`, `5432` |
| `CC_DB_NAME`, `CC_DB_USER`, `CC_DB_PASSWORD` | PostgreSQL credentials | environment-specific |
| `CC_DB_AUTO_MIGRATE` | Apply migrations during startup | `0` outside local development |
| `CC_EMBEDDING_BACKEND` | `auto`, `lexical`, or `bge` retrieval | `lexical` for lightweight runs |
| `CC_RERANKER` | `auto`, `lexical`, or `cross` reranking | `lexical` |
| `CC_MATCH_LLM` | Enable constrained LLM selection | `0` or `1` |
| `CC_MATCH_LLM_PROVIDER` | `ollama`, `anthropic`, or `gemini` | `ollama` |
| `CC_MATCH_MODEL` | Provider-specific model name | `qwen3:8b` |
| `CC_INCLUDE_MOCK_COURSES` | Include labelled synthetic course maps | `0` or `1` |

Never commit `.env`, database passwords, service tokens, or hosted-provider keys.

## PostgreSQL migrations

The AI database is separate from the backend's MySQL/H2 application database. The two schemas
must not be mixed.

After configuring `CC_DB_*`, migrate the AI database with:

```bash
uv run cc-db-migrate
# equivalent
uv run python -m careercompass.db.migrate
```

The migrator acquires a PostgreSQL advisory lock, verifies stored SHA-256 checksums, and applies
pending numbered migrations transactionally. Never edit a migration that has already been
applied; create the next numbered migration instead. Keep `CC_DB_AUTO_MIGRATE=0` in production and
run migrations as an explicit deployment step after a backup.

## Run the API

```bash
uv run uvicorn careercompass.api.app:app --reload --host 127.0.0.1 --port 8000
```

Useful URLs:

| URL | Purpose |
|---|---|
| `http://localhost:8000/docs` | Interactive OpenAPI documentation |
| `http://localhost:8000/api/v1/health/live` | Process liveness |
| `http://localhost:8000/api/v1/health/ready` | Matcher and data readiness |

The major endpoint groups cover transcript parsing, syllabus preview and extraction, extraction
review, courses and career paths, skill vectors and gaps, recommendations, quizzes, mentor
matching, taxonomy matching, and the review queue. FastAPI generates the current OpenAPI schema at
`/openapi.json` and renders it interactively at `/docs`.

## Command-line tools

```bash
uv run cc-build-taxonomy
uv run cc-parse-transcript path/to/plan.pdf
uv run cc-parse-syllabus path/to/syllabus.pdf
uv run cc-extract-skills path/to/syllabus.pdf --match
uv run cc-match-skills path/to/syllabus.pdf
uv run cc-db-migrate
```

## Test

Run the deterministic lexical suite used by CI:

```bash
CC_EMBEDDING_BACKEND=lexical CC_API_WARMUP=0 uv run --extra dev pytest -q
```

To validate the generated OpenAPI schema:

```bash
CC_API_WARMUP=0 uv run --extra dev python -c "from openapi_spec_validator import validate; from careercompass.api.app import app; validate(app.openapi())"
```

## Docker

The repository's `compose.yaml` starts this service with PostgreSQL, lexical retrieval, and local
Ollama. From the project root:

```bash
docker compose up --build ai-service postgres
```

The development Compose file publishes FastAPI on `127.0.0.1:8000` and PostgreSQL on
`127.0.0.1:5433`.
