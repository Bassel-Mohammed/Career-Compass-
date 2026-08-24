# ADR-007: Database migration framework

- Status: Accepted
- Date: 2026-08-23

## Context

The Java backend previously relied on Hibernate schema behavior. Opaque IDs,
qualified course identity and versioned AI results require repeatable upgrades
without guessing or destroying legacy data.

## Decision

Use Flyway for Java-owned MySQL and H2-compatible schema migrations. Establish
an operator-reviewed baseline before entity changes. Initial migrations are
additive and nullable where legacy meaning is unresolved. Use temporary
dual-read/dual-write where required; apply non-null/unique constraints only
after verified backfills.

Generate opaque IDs for Java-owned entities. Do not infer course codes, skill
IDs or career-path codes from names without an approved mapping. Preserve
legacy numeric keys and display names during v1. Store immutable validated
skill-vector/result documents plus any documented normalized current
projection and auditable version/correlation metadata.

## Consequences

Fresh-schema, upgrade, rollback-mode and unresolved-backfill tests are release
gates. Runtime rollback disables the integration feature or redeploys the last
compatible service; additive migrations are not destructively reversed.

## Implementation

Flyway is enabled in every backend profile and Hibernate now validates rather than mutates the
schema. `V1` captures the final hand-managed schema, including `academic_records.course_code`.
The `V2` Java compatibility bridge conditionally adds quiz skill identity so an operator-baselined
database also upgrades when it already received the former hand-run quiz migration. `V3` bridges
the small MySQL/H2 `ALTER COLUMN` syntax difference, and `V4` adds integrity constraints plus the
nullable canonical identity and projection-provenance foundation.

Fresh databases run the complete chain. A populated unmanaged database must be backed up,
preflighted, and explicitly baselined at version 1 once; automatic baseline guessing remains
disabled. The executable procedure is documented in `backend/db/README.md`.

Skill and career-path IDs are stable and title/label independent for new writes. Existing rows are
left nullable until an approved mapping or safe lazy backfill is available. Skill display names
remain unique during this first compatibility phase; supporting two canonical skills with the same
label requires a later reviewed migration and UI disambiguation policy.
