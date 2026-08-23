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

## Test

```bash
cd backend
mvn test
```

The AI integration defaults to the mock implementation. To use the FastAPI
service after aligning the endpoint contract, set `careercompass.ai-service.use-mock`
to `false` and configure `AI_SERVICE_BASE_URL` when necessary.

The reference SQL schema is at [`db/schema.sql`](db/schema.sql).
