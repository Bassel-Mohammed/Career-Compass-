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
shared service token. All published ports bind to `127.0.0.1`, and no MySQL or
PostgreSQL container is started.

The default stack deliberately disables optional model downloads and LLM calls.
Transcript parsing, skill dashboards, gaps, recommendations, and matching use
the versioned runtime artifacts and lexical backend; quiz generation remains
unavailable because it requires a configured LLM. Large rebuild caches stay out
of Git, while the taxonomy, course-skill maps, and career-path ontology needed by
a fresh clone are versioned with the application.

The real AI service deliberately returns 501 for the descoped job-matching
capability. To demonstrate the employer candidate list with the UI's clearly
labelled placeholder scores, start the same stack with the Java mock enabled:

```bash
BACKEND_USE_AI_MOCK=true docker compose up --build
```

H2 account/upload metadata persists in the `backend_h2` named volume, and the
PDF bytes persist in `learning_outcomes`, so stored uploads remain discoverable
after a restart. Stop the stack with `docker compose down`; add `--volumes` only
when you also want to erase the H2 data and uploaded files.

The checked-in token and JWT defaults are for loopback development only. Set
`AI_SERVICE_TOKEN` and `JWT_SECRET` in a root `.env` file before sharing the
stack or changing its host bindings.

## Integration status

The former `Backend` and `mohammed` branches are combined in this tree. Their
files do not collide except for the root README and `.gitignore`, which have
been consolidated.

Java and Python share the versioned internal contract in
[`careercompass-ai-internal-v1.yaml`](docs/contracts/careercompass-ai-internal-v1.yaml).
The real Java HTTP client and cross-runtime contract checks live under
[`backend/src/test/java/com/careercompass/integration/ai/`](backend/src/test/java/com/careercompass/integration/ai/).
