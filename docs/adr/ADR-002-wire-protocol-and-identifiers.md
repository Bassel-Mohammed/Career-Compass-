# ADR-002: Wire protocol, naming and canonical identifiers

- Status: Accepted
- Date: 2026-08-23

## Context

The old Java client uses unversioned Java-shaped payloads while FastAPI exposes
different versioned Pydantic schemas. Database integers and display names are
not stable identities across services.

## Decision

- The canonical base path is `/api/v1`; the source of truth is
  `docs/contracts/careercompass-ai-internal-v1.yaml`.
- JSON property names and multipart text-part names use `snake_case`.
- Java transport records and mappers isolate this wire model from Java domain
  and public DTOs. Python's internal model likewise must not define Java's
  public API.
- Student, job, candidate, mentor, operation, quiz and vector IDs are opaque,
  non-empty strings. Clients must not parse their format.
- Career paths use immutable `career_path_code`; names are display-only.
- Skills use canonical `skill_id`; labels are display-only.
- A course is identified by `institution_code`, `catalog_version` and
  `course_code`. The current MEU data may use one institution value but may not
  discard the other identity fields.
- Additive optional fields are compatible. Removing/renaming a field, changing
  meaning/type/range, making an optional field required, or removing an enum
  value requires a new API version.

## Consequences

Legacy numeric primary keys stay internal to Java. Name-to-ID guesses are not
allowed: unresolved historical rows remain explicitly unresolved until a
reviewed mapping exists. Every request and response is validated at the
boundary, and shared examples become executable contract fixtures.
