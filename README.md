# CareerCompass

CareerCompass is an AI-powered skills enhancement and job-matching platform.
The repository contains two backend services and a dedicated location for the
web interface.

## Project structure

```text
career_compass/
├── backend/       Java 17 + Spring Boot API, authentication, and business logic
├── ai-service/    Python + FastAPI analysis, extraction, and matching service
├── frontend/      Web UI workspace
└── docs/          Cross-service contracts
```

Service-specific setup and test instructions are documented in
[`backend/README.md`](backend/README.md) and
[`ai-service/README.md`](ai-service/README.md).

## Local services

| Component | Default URL | Purpose |
|---|---|---|
| Spring Boot API | `http://localhost:8080` | Public API used by the UI |
| FastAPI service | `http://localhost:8000` | Internal AI/data-analysis API |
| Frontend | `http://localhost:5173` | Browser application |

The frontend should communicate with Spring Boot. Spring Boot is responsible
for authentication, authorization, persistence, and calls to the internal
FastAPI service.

## Docker development stack

Run all three services with Docker Compose:

```bash
docker compose up --build
```

Then open `http://localhost:5173`. Compose keeps the browser API URL at
`http://localhost:8080`, while Spring reaches FastAPI through the private
service URL `http://ai-service:8000`. It uses Spring's seeded H2 `dev` profile,
the real HTTP AI client, deterministic lexical AI backends, and a local-only
shared service token. No MySQL or PostgreSQL container is started.

The default stack deliberately disables optional model downloads and LLM calls.
Transcript parsing, skill dashboards, gaps, recommendations, and matching use
the versioned runtime artifacts and lexical backend; quiz generation remains
unavailable because it requires a configured LLM. Large rebuild caches stay out
of Git, while the taxonomy, course-skill maps, and career-path ontology needed by
a fresh clone are versioned with the application.

Uploaded learning-outcome PDFs persist in the `learning_outcomes` named volume.
Stop the stack with `docker compose down`; add `--volumes` only when you also
want to erase those uploads. Set `AI_SERVICE_TOKEN` in a root `.env` file to
override the development-only default for both backend services.

## Integration status

The former `Backend` and `mohammed` branches are combined in this tree. Their
files do not collide except for the root README and `.gitignore`, which have
been consolidated.

Java and Python share the versioned internal contract in
[`careercompass-ai-internal-v1.yaml`](docs/contracts/careercompass-ai-internal-v1.yaml).
The real Java HTTP client and cross-runtime contract checks live under
[`backend/src/test/java/com/careercompass/integration/ai/`](backend/src/test/java/com/careercompass/integration/ai/).
