# ADR-001: Service and data ownership

- Status: Accepted
- Date: 2026-08-23
- Scope: Java backend and Python AI service

## Context

Both runtimes currently contain overlapping representations of academic and
derived data. Without one authoritative owner, corrections, authorization and
AI results can diverge.

## Decision

Java is the system of record and owns authentication, authorization, users,
career-path definitions, confirmed transcripts and corrections, jobs,
candidates, mentors, consultations, approved learning outcomes/course maps,
quiz attempts and grades, and durable business-facing AI result references.

Python owns computation: transcript/syllabus extraction, Student Skill Vector
calculation, gaps, grounded recommendations, quiz generation and validation,
and job matching. It owns model/taxonomy/catalog indexes, provider settings,
caches and durable async-operation state. It may not become the authoritative
store for a student's transcript, job, mentor, quiz attempt or approved map.

Python-derived records must retain Java-issued opaque IDs and data/version
metadata. The browser calls Java only. Java calls Python only through its
integration adapter and the internal v1 contract.

## Consequences

- Java validates and persists approved outcomes; Python returns proposals or
  derived results.
- Python can rebuild derived indexes from approved, versioned input.
- Syllabus mappings require Java review before publication.
- Raw transcript contents, answer keys and tokens are excluded from logs.
- Existing duplicate Python artifacts require classification as an index,
  cache, async state or legacy data before production rollout.
