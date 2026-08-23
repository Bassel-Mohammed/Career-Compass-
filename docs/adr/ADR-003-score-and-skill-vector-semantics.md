# ADR-003: Scores and Student Skill Vector semantics

- Status: Accepted
- Date: 2026-08-23

## Context

The existing boundary mixes `0..100` Java values with Python `0..1` values and
can compute different skill profiles from reduced inputs.

## Decision

All internal proficiency, coverage, gap, readiness, relevance, confidence,
weight and normalized-grade values are decimals from `0.0` through `1.0`.
Only Java's public/UI mapper converts them to percentages. Wire
classifications are lowercase `strong`, `moderate` or `weak`.

Python is the only component that computes or recomputes a Student Skill
Vector. Java submits confirmed qualified courses and graded quiz evidence,
then stores the returned immutable document/version and an explicit current
projection. Gap, recommendation, quiz and matching operations use that exact
document or version, rather than reconstructing a vector from labels.

Each derived result identifies its input `vector_version` and relevant
taxonomy, course-map, scoring/algorithm and contract versions. Python rejects
incompatible expected versions with a controlled `409` problem.

## Consequences

- Java grades quizzes, but sends score evidence back to Python for a new vector.
- Skill labels and course names never substitute for canonical IDs.
- Range, scale and vector-version preservation are mandatory mapper and
  cross-runtime tests.
- Algorithm or threshold changes publish new version metadata; they do not
  silently reinterpret stored values.
