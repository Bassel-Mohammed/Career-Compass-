# ADR-005: Mentor matching scope

- Status: Accepted — AI ranking deferred
- Date: 2026-08-23

## Context

Canonical functional requirements require viewing mentors and booking a
consultation. Some AI planning material additionally describes AI-ranked
mentor matching. That stronger interpretation has not been approved.

## Decision

Secure mentor listing and consultation booking remain Java responsibilities
and are mandatory. AI mentor ranking is an optional v1 capability and is not a
core-release gate. The OpenAPI operation is documented with
`x-careercompass-optional: true`; deployments may omit/disable it and return a
controlled `501` problem.

Enabling the operation requires explicit product/supervisor approval and tests
for authorization, active-mentor filtering, grounded IDs, explanation and
score semantics. Booking remains in Java in all cases.

## Consequences

Core job matching can ship without an unsupported claim that mentor AI is
complete. A later decision that makes ranking mandatory must supersede this
ADR and update requirements traceability and acceptance gates.
