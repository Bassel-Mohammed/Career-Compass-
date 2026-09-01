# CareerCompass Spring Backend

The backend is the public API and workflow layer for CareerCompass. It authenticates users, applies
role-based authorization, persists application data, manages uploads and business workflows, and
calls the internal FastAPI service for AI operations.

## Technology

- Java 17 and Spring Boot 3.3
- Spring Security with bearer JWTs and logout-token invalidation
- Spring Data JPA and Bean Validation
- Flyway-managed H2 and MySQL schemas
- Spring WebClient for the internal AI API
- Springdoc OpenAPI/Swagger UI

## Requirements

- JDK 17
- Maven 3.9+ or a compatible system Maven
- FastAPI service only when using the real AI client
- MySQL 8.4 for the production profile

Verify that Maven is using Java 17:

```bash
java -version
mvn -version
```

## Run locally

The default `dev` profile uses in-memory H2 and the mock AI client. A JWT signing secret is required:

```bash
cd backend
JWT_SECRET=local-development-secret-at-least-32-characters mvn spring-boot:run
```

| URL | Purpose |
|---|---|
| `http://localhost:8080/swagger-ui.html` | Interactive public API documentation |
| `http://localhost:8080/v3/api-docs` | OpenAPI JSON |
| `http://localhost:8080/actuator/health` | Application health |
| `http://localhost:8080/h2-console` | Development H2 console |

H2 development connection values:

```text
JDBC URL: jdbc:h2:mem:careercompass
User: sa
Password: (blank)
```

The database is recreated when the standalone development process restarts. The Docker development
stack overrides the URL with file-backed H2 so its data persists in a named volume.

## Use the real AI service

The `integration` profile disables the mock client and points to FastAPI:

```bash
JWT_SECRET=local-development-secret-at-least-32-characters \
AI_SERVICE_BASE_URL=http://localhost:8000 \
AI_SERVICE_TOKEN=careercompass-local-dev-token \
SPRING_PROFILES_ACTIVE=integration \
mvn spring-boot:run
```

The token must equal the AI service's `CC_SERVICE_TOKEN`. The frontend must continue to call Spring
Boot, never FastAPI directly.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET` | Always | JWT signing secret; use a long random value outside tests |
| `SPRING_PROFILES_ACTIVE` | No | `dev`, `integration`, or `prod`; defaults to `dev` |
| `AI_SERVICE_BASE_URL` | Real AI/prod | FastAPI base URL |
| `AI_SERVICE_TOKEN` | Real AI/prod | Shared service bearer token |
| `CORS_ALLOWED_ORIGINS` | Deployment | Comma-separated browser origins |
| `LEARNING_OUTCOMES_DIR` | No | Directory for uploaded learning-outcome PDFs |
| `DB_URL` | Production | MySQL JDBC URL |
| `DB_USERNAME` | Production | MySQL user |
| `DB_PASSWORD` | Production | MySQL password |

Sessions expire after 30 minutes. Transcript uploads are limited to 10 MB. Only health and info
actuator endpoints are exposed over HTTP.

## API areas

- Authentication and password/logout operations for all five roles
- Student profile, transcript, skill dashboard, career skills, recommendations, quizzes, jobs, and appointments
- Employer profile, job posting CRUD, and ranked candidates
- Mentor profile, availability, session decisions, outcomes, and student progress views
- Content-manager learning-outcome upload, extraction review, skill editing, and publication
- Administrator accounts and reference data
- Public study fields, career paths, and universities

Swagger UI is the authoritative interactive reference for request and response fields.

## Database migrations

Flyway owns the schema in every profile; Hibernate only validates that the entities match it.
Executable migrations are under `src/main/resources/db/migration`. `db/schema.sql` is a human-readable
snapshot for review and diagrams and must not be used to initialize a database.

A fresh database migrates automatically. A populated database created before Flyway requires an
operator-reviewed one-time baseline. Follow [`db/README.md`](db/README.md); never enable
`baseline-on-migrate` permanently and never edit an applied migration.

The backend database is MySQL/H2. It is separate from the AI service's PostgreSQL database, even
where table names happen to overlap.

## Test and build

```bash
# Full test suite
mvn test

# Compile tests without running them
mvn clean test-compile

# Build the executable JAR
mvn clean package
```

Tests receive an explicit test-only JWT secret from Maven configuration. The suite covers security,
controllers, services, persistence, migrations, and the Spring/FastAPI integration contract.

## Docker

From the repository root, start the backend with its dependencies:

```bash
docker compose up --build backend
```

The local Compose stack uses persistent H2, the real FastAPI client, and loopback-only published
ports. Set `BACKEND_USE_AI_MOCK=true` before the command to use explicitly labelled mock AI data.

## Canonical skill identity

Career paths use stable `careerPathCode` values, and skills can carry a unique
`canonicalSkillId`. Real AI vectors are joined using the canonical ID rather than a mutable display
label. `taxonomyVersion` records the taxonomy source, while each projection refresh receives its
own `vectorVersion`; conflicting canonical identities are rejected for manual review.
