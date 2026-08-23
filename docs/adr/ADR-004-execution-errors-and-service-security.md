# ADR-004: Execution, errors, retries and service security

- Status: Accepted
- Date: 2026-08-23

## Context

AI operations have different latency and retry characteristics. Raw framework
errors, one generic timeout and an unauthenticated boundary cannot support a
safe production integration.

## Decision

- Transcript parsing, vector/gap calculation, recommendations, quizzes and
  bounded job-match batches are synchronous only within documented budgets.
- Full syllabus extraction is asynchronous: submit returns `202`, `Location`
  and an operation; callers poll or request idempotent cancellation.
- Errors use `application/problem+json` and RFC 9457 fields plus a stable
  application `code`, `correlation_id` and optional invalid parameters.
- Every request must carry `X-Correlation-ID`; every response echoes it.
- Async submission requires `Idempotency-Key`. Repeating the same key and body
  returns the same operation; reusing it with different content returns `409`.
- Retry only idempotent transient connection failures and `502/503/504`, with
  bounded exponential backoff and jitter. Never retry validation or auth errors.
- Internal routes use an HTTP Bearer service token. Production also requires
  TLS and network policy; localhost HTTP is allowed only for local/integration
  profiles. Tokens never appear in source, responses or logs.
- Long operations remain async rather than receiving unbounded timeouts.

## Consequences

Java must decode Problem Details and expose controlled application errors.
Python must preserve correlation IDs in problems/logs and maintain durable
idempotency/operation state before multi-instance deployment. Rate limits and
per-operation deadlines are verified before production enablement.
