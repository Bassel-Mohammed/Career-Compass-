# ADR-006: Cross-runtime test harness

- Status: Accepted
- Date: 2026-08-23

## Context

Isolated mocked tests did not detect path, content-type and schema drift. A JVM
test cannot directly host an in-process ASGI application.

## Decision

The baseline integration harness starts the real FastAPI application as a
managed subprocess on a free local port with isolated temporary data and
deterministic taxonomy/catalog/LLM fixtures. It polls authenticated
`/api/v1/health/ready`, then runs Java Maven Failsafe tests with
`use-mock=false`. It captures sanitized logs and always terminates the process.

Contract fixtures are shared from a neutral test-fixture directory and must
validate against OpenAPI. Real routes, Pydantic validation, JSON/multipart
serialization and Java deserialization are exercised. Optional live-provider
smoke tests remain separate from deterministic CI.

## Consequences

No capability is called integrated based only on unit tests or mocks. CI needs
a JDK and supported Python environment. Docker/Testcontainers may be added,
but the subprocess harness remains available for environments without Docker.
