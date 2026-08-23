# CareerCompass internal AI contracts

`careercompass-ai-internal-v1.yaml` is the machine-readable source of truth for
communication from the Java backend to the Python AI service. Java's public
browser API is intentionally a different boundary.

## Contract status

- Current implementation target: `careercompass-ai-internal-v1.yaml`
- Historical contract: `AI_SERVICE_CONTRACT.docx`
- Historical status: **superseded on 2026-08-23**; retained for audit only

The DOCX must not be used to generate clients, routes or fixtures. It is not
deleted or edited because it records the previous agreement.

## Compatibility policy

Changes may be made in v1 without a new base path only when existing valid
requests and responses remain valid. New optional fields, endpoints and
non-required enum handling guidance are normally additive. Removed/renamed
fields, changed types/ranges/semantics, new required fields, removed enum
values or changed authentication/idempotency rules are breaking and require a
new version or a negotiated transition.

All internal calls use snake_case JSON, opaque string IDs, Bearer service
authentication and `X-Correlation-ID`. Async extraction submission additionally
requires `Idempotency-Key`. Errors are RFC 9457 Problem Details.

## Validation

At minimum, parse the document as YAML and verify it has OpenAPI `3.1.x`,
`paths` and `components`. CI should add an OpenAPI 3.1 validator/linter and
validate all shared fixtures against their referenced schemas.
