# CareerCompass architecture decisions

These decisions define the Java-to-Python internal API v1. They apply only to
the service boundary; Java's browser-facing API remains independent.

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](ADR-001-service-and-data-ownership.md) | Service and data ownership | Accepted |
| [ADR-002](ADR-002-wire-protocol-and-identifiers.md) | Wire naming, API versioning and identifiers | Accepted |
| [ADR-003](ADR-003-score-and-skill-vector-semantics.md) | Scores and Student Skill Vector semantics | Accepted |
| [ADR-004](ADR-004-execution-errors-and-service-security.md) | Async work, errors, retries and service security | Accepted |
| [ADR-005](ADR-005-mentor-matching-scope.md) | Mentor matching scope | **Superseded by ADR-008** |
| [ADR-006](ADR-006-cross-runtime-test-harness.md) | Cross-runtime test harness | Accepted |
| [ADR-007](ADR-007-database-migration-framework.md) | Database migration framework | Accepted |
| [ADR-008](ADR-008-mentor-matching-in-scope.md) | Mentor matching is in scope for v1 | Accepted |

Accepted means the decision is the implementation baseline for internal API
v1. Reversing one requires a superseding ADR and, after a runtime consumer is
released, the contract's breaking-change process.
