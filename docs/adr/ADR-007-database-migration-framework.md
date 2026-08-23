# ADR-007: Database migration framework

- Status: Accepted
- Date: 2026-08-23

## Context

The Java backend currently relies on Hibernate schema behavior. Opaque IDs,
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
