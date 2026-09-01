# CareerCompass Spring Backend

The Spring Boot service owns authentication, role-based access control,
business workflows, persistence, and the public API consumed by the frontend.

## Requirements

- Java 17
- Maven 3.9+

## Run locally

```bash
cd backend
mvn spring-boot:run
```

- API: `http://localhost:8080`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- H2 console: `http://localhost:8080/h2-console`
- H2 JDBC URL: `jdbc:h2:mem:careercompass`

The `dev` profile uses H2. The `prod` profile uses MySQL and requires
`DB_URL`, `DB_USERNAME`, and `DB_PASSWORD`.

Flyway owns the database schema in every profile and Hibernate runs in validation mode. A new
database is migrated automatically from the packaged `V1` baseline to the latest version. Do not
initialize the database with `db/schema.sql`; that file is only a readable snapshot for review and
diagrams.

An existing hand-created database needs an operator-reviewed, one-time Flyway baseline before the
application can migrate it. See [`db/README.md`](db/README.md) for the preflight requirements and
exact procedure. Do not turn on `baseline-on-migrate` as a permanent setting.

## Test

```bash
cd backend
mvn test
```

The AI integration defaults to the mock implementation. To use the FastAPI
service after aligning the endpoint contract, set `careercompass.ai-service.use-mock`
to `false` and configure `AI_SERVICE_BASE_URL` when necessary.

## Canonical identities and AI provenance

New career paths receive stable, title-independent `careerPathCode` values. Seeded paths use
reviewed `career:*` codes; API-created paths use the supplied code or an opaque `cp:<uuid>` code.
Existing career-path rows remain valid with a null code until an approved backfill is available.

Skills now have a nullable, unique `canonicalSkillId`. A real AI skill-vector response is joined by
that ID, not its mutable display label. If an old label-keyed skill has no canonical ID, the next
matching response can claim it as a safe lazy backfill; an ID conflict is rejected for manual
review. `taxonomyVersion` is stored on skills and projections, while every projection refresh gets
an opaque `vectorVersion`. The legacy unique skill-name rule remains during this transition, so
taxonomies containing distinct canonical skills with the same label require an explicit data-model
migration before import.

The reference snapshot is [`db/schema.sql`](db/schema.sql); the executable migration chain is under
[`src/main/resources/db/migration`](src/main/resources/db/migration).
