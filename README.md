# CareerCompass Backend

Backend for **CareerCompass** — "AI-powered Skills Enhancement and Job Matching System"
(MEU Graduation Project, Basil Mohammad & Mohammed Al-Madhoun, supervised by Dr. Shadi Ettantawi).

Built with **Java 17 + Spring Boot 3**, implementing the Container-level "Backend" component
described in the project report (Section 5.1), organised into:

```
Security Layer -> Business Layer -> Integration Layer -> Data Access Layer
```

The **Data Analyses Layer** (NLP, embeddings, skill-vector computation) is a *separate* Python/FastAPI
service developed independently and consumed via REST through the Integration Layer.

## Running locally (dev profile, H2 in-memory DB)

```bash
mvn spring-boot:run
```

- API base URL: `http://localhost:8080`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- H2 console: `http://localhost:8080/h2-console` (JDBC URL: `jdbc:h2:mem:careercompass`)

## Profiles

| Profile | Database | Notes |
|---|---|---|
| `dev` (default) | H2 in-memory | Fast local development/testing |
| `prod` | MySQL | Requires `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` env vars |

## Documentation

Increment-by-increment build documentation lives in [`docs/`](./docs), one file per development
increment, describing what was built, key decisions, and open items.
