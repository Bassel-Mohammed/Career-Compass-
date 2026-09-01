# CareerCompass

CareerCompass is a full-stack career-readiness platform that converts academic records and
learning outcomes into a skills profile. Students can identify skill gaps, receive course and job
recommendations, take generated quizzes, and connect with mentors. Employers, content managers,
mentors, and administrators have dedicated role-based workspaces.

## Architecture

```text
React + TypeScript browser
          |
          v
Spring Boot public API ---- MySQL / H2
          |
          v
FastAPI internal AI API --- PostgreSQL + taxonomy artifacts + LLM
```

The browser calls only the Spring Boot API. Spring owns authentication, authorization, application
data, and workflows; it calls FastAPI with a service token for transcript parsing, skill analysis,
recommendations, quiz generation, and matching.

| Component | Technology | Local URL |
|---|---|---|
| Frontend | React 19, TypeScript, Vite | `http://localhost:5173` |
| Backend | Java 17, Spring Boot 3 | `http://localhost:8080` |
| AI service | Python 3.10+, FastAPI | `http://localhost:8000` |
| AI database | PostgreSQL 16 | `localhost:5433` |
| Database browser | Adminer | `http://localhost:8081` |

## Main features

- Five authenticated roles: student, employer, mentor, content manager, and administrator.
- Transcript PDF parsing, editable course review, and a versioned student skill vector.
- Career-path skill-gap analysis with demand, coverage, and proficiency explanations.
- Ranked course recommendations and AI-generated quizzes.
- Mentor discovery, appointment requests, availability, session decisions, and outcomes.
- Employer job-posting management and candidate ranking.
- Learning-outcome upload, AI extraction review, skill replacement, and publication.
- Administrator management of content managers, mentors, study fields, career paths, and universities.

## Repository layout

```text
career_compass/
├── frontend/       React application and browser tests
├── backend/        Spring Boot public API and MySQL/H2 migrations
├── ai-service/     FastAPI AI service and PostgreSQL migrations
├── scripts/        Database and integration verification scripts
├── compose.yaml    Local development stack
└── docker-compose.prod.yml
```

Detailed instructions are available in the service READMEs:

- [Frontend](frontend/README.md)
- [Spring Boot backend](backend/README.md)
- [AI service](ai-service/README.md)

## Quick start with Docker

### Requirements

- Docker Engine with the Compose plugin
- Linux for the current host-network development configuration
- Optional: [Ollama](https://ollama.com/) with `qwen3:8b` for local LLM-backed matching and quizzes

Start the complete development stack from the repository root:

```bash
docker compose up --build
```

Open `http://localhost:5173`. The first AI-service startup can take several minutes while its
matcher is initialized. The development stack uses:

- file-backed H2 for Spring application data;
- PostgreSQL for AI extraction/review data;
- lexical retrieval and reranking;
- Ollama at `http://localhost:11434` for ambiguous matching and quiz generation;
- local-only default secrets and loopback-bound ports.

To run the backend with explicitly labelled mock AI results:

```bash
BACKEND_USE_AI_MOCK=true docker compose up --build
```

Stop services without deleting their data:

```bash
docker compose down
```

Use `docker compose down --volumes` only when you intentionally want to erase local H2,
PostgreSQL, and uploaded learning-outcome data.

## Run services separately

Start each service in its own terminal. See the linked service README for environment details.

```bash
# AI service
cd ai-service
uv sync --extra dev
uv run uvicorn careercompass.api.app:app --reload --port 8000

# Backend (mock AI client by default)
cd backend
JWT_SECRET=local-development-secret-at-least-32-characters mvn spring-boot:run

# Frontend
cd frontend
npm ci
npm run dev
```

## Verification

Run the same main checks used by CI:

```bash
(cd frontend && npm ci && npm run test -- --run && npm run build && npm run lint)
(cd backend && mvn test)
(cd ai-service && uv sync --extra dev && CC_EMBEDDING_BACKEND=lexical CC_API_WARMUP=0 uv run pytest -q)
python3 scripts/check_database_migration_layout.py
```

CI additionally verifies MySQL and PostgreSQL migration paths and validates the OpenAPI schema
generated directly by the FastAPI application.

## Production

`docker-compose.prod.yml` defines Caddy, the production frontend image, Spring Boot, FastAPI,
MySQL, and PostgreSQL. Create a root `.env` containing at least:

```dotenv
PUBLIC_HOST=careercompass.example.com
MYSQL_ROOT_PASSWORD=replace-me
MYSQL_PASSWORD=replace-me
POSTGRES_PASSWORD=replace-me
JWT_SECRET=replace-with-a-long-random-secret
AI_SERVICE_TOKEN=replace-with-a-long-random-token
GEMINI_API_KEY=replace-me
```

The Compose file mounts a root `Caddyfile`; make sure that deployment configuration exists before
starting the stack. Start the databases, run the explicit AI migration, and then start the full
application:

```bash
docker compose -f docker-compose.prod.yml up -d mysql postgres
docker compose -f docker-compose.prod.yml run --rm ai-service python -m careercompass.db.migrate
docker compose -f docker-compose.prod.yml up --build -d
```

Production secrets must never be committed. Back up both databases and run the AI database
migration as a controlled deployment step; `CC_DB_AUTO_MIGRATE` is intentionally disabled in the
production Compose file.
