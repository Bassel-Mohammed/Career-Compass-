# Backend database files

`schema.sql` is a readable snapshot of the **latest** Java-owned MySQL schema. It is useful for
review and database diagrams, but it is not an initializer and must not be run before or after the
versioned migrations.

Flyway owns runtime schema changes. Its packaged migration chain is in
`src/main/resources/db/migration`:

- `V1__baseline.sql` is the last hand-managed schema. It already contains
  `academic_records.course_code`, so there is no second migration that tries to add that column.
- `V2__add_quiz_skill_identity` is a small JDBC metadata migration under
  `src/main/java/db/migration`. It adds canonical quiz skill identity, or records the migration as
  complete when the former hand-run quiz migration already added the column and index.
- `V3__align_quiz_option_column_types` is the narrow dialect bridge for MySQL/H2 column-alter
  syntax.
- `V4__canonical_identity_and_quiz_integrity.sql` adds quiz/score integrity constraints and
  introduces nullable canonical identity and vector provenance fields.

## Empty database

Start the backend normally. Flyway applies V1 through the latest version before Hibernate validates
the entity mappings.

## Existing hand-created database

Do not enable `baseline-on-migrate` permanently. First back up and inspect the database. It must
match V1, including `academic_records.course_code`, and it must not contain duplicate quiz responses
for the same `question_id` or scores outside `0..100`.

After that review, baseline it at version `1` once, then run `migrate`. One Spring Boot-compatible
way is to set these only for the first controlled startup:

```bash
SPRING_FLYWAY_BASELINE_ON_MIGRATE=true \
SPRING_FLYWAY_BASELINE_VERSION=1 \
SPRING_PROFILES_ACTIVE=prod \
java -jar app.jar
```

Remove the two baseline variables immediately after Flyway records and applies the upgrade. If the
database predates `academic_records.course_code`, apply an operator-reviewed course-code migration
before baselining rather than guessing values or changing the baseline version.

Old Hibernate-generated development volumes are not a supported production upgrade source. Rebuild
the disposable local volume so Flyway can create it from V1; never remove a real database volume.
