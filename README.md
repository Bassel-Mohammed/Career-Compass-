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
| Frontend | `http://localhost:5173` | Planned browser application |

The frontend should communicate with Spring Boot. Spring Boot is responsible
for authentication, authorization, persistence, and calls to the internal
FastAPI service.

## Integration status

The former `Backend` and `mohammed` branches are combined in this tree. Their
files do not collide except for the root README and `.gitignore`, which have
been consolidated.

The service-to-service API contract still needs alignment before real AI calls
can replace the Spring mock client. See
[`docs/contracts/AI_SERVICE_CONTRACT.docx`](docs/contracts/AI_SERVICE_CONTRACT.docx)
and [`ai-service/docs/API_DESIGN.md`](ai-service/docs/API_DESIGN.md).
