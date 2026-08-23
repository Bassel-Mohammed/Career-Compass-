# CareerCompass Java ↔ Python Integration Fix Plan

**Status:** In progress — see §16 for live milestone status  
**Plan date:** 23 August 2026  
**Repository branch:** `integration/full-stack`  
**Baseline commit:** `042724a38872e51bfc247b01fe3b38a23a9b99c0`  
**Related audit:** `docs/compatibility/CareerCompass_Java_Python_Compatibility_Report.md`  
**Planning baseline:** `/home/almadhoun/Desktop/CareerCompass`

> **Scope decision (24 August 2026):** job matching (**M7**) and mentor AI ranking (**M9**)
> are **descoped for the current release** by owner decision. `/api/v1/job-matches/*` and
> `/api/v1/mentor-matches` are therefore excluded from the v1 contract, and the job/mentor
> acceptance criteria in §11 do not gate this release. Java's existing mentor list/booking
> behaviour is unaffected and must not be removed. The plan text for M7/M9 is retained
> below unchanged so the work can be picked up later without re-planning.
>
> Implementation began on 24 August 2026; §16 records what is actually done.

## 1. Plan assessment

The supplied remediation plan is technically strong and should be adopted as the basis of the integration work. It correctly requires a canonical contract, stable identifiers, a shared Student Skill Vector, a Java anti-corruption adapter, real FastAPI routes, migrations, job matching, controlled errors, and cross-runtime tests.

It should not be executed as one large change. Before implementation, the following corrections are incorporated into this official plan:

- Decide data ownership, identifiers, vector semantics, async behavior, and optional scope in Architecture Decision Records (ADRs) **before** freezing OpenAPI.
- Deliver the work as reversible vertical increments, beginning with the five Python capabilities that already exist.
- Treat job matching as a separate milestone and mentor matching as an approval-gated scope decision.
- Define course identity as institution/catalog-qualified course code, while retaining `course_code` as the deterministic course key for the current MEU data.
- Introduce Java-owned opaque integration IDs for people, jobs, and mentors instead of sending database-local integers.
- Make Python the only component that computes or recomputes a Student Skill Vector. Java grades quizzes and persists evidence; Python returns the new vector version.
- Specify a real cross-runtime test harness. A JVM test cannot directly host an in-process ASGI application.
- Use real FastAPI routes and algorithms with deterministic test providers/fixtures in CI; keep optional live-LLM tests separate.
- Define idempotency, authentication, correlation, errors, and async operation envelopes in contract v1 rather than adding them after implementation.
- Interpret “no `422` mismatch” as: every **valid canonical fixture** must pass. Invalid requests must continue to return a controlled `422`.
- Do not claim completion if Java compilation or the cross-runtime E2E suite cannot run.

## 2. Objective

Replace the current disconnected behavior:

```text
Java → unversioned path → 404
Java-shaped body → nearest Python path → 422
Java default runtime → mock only
```

with this boundary:

```text
Browser / UI
    ↓
Java public API, authentication, orchestration and persistence
    ↓
DataAnalysisClient domain interface
    ↓
Java internal-API transport adapter and mappers
    ↓
docs/contracts/careercompass-ai-internal-v1.yaml
    ↓
versioned FastAPI internal routes
    ↓
Python AI/data-analysis modules
    ↓
schema-validated response or RFC 9457 problem
    ↓
Java validation, domain persistence and public response
```

The browser must never call FastAPI directly.

## 3. Ownership model

### Java owns durable business state

- Users, roles, authorization and public identities.
- Career-path selection and approved career-path definitions.
- Confirmed academic records and user corrections.
- Jobs, candidates, mentors, consultations and access rules.
- Approved learning outcomes and approved course-to-skill mappings.
- Quiz definitions shown to the user, attempts, answers and grades.
- Version references for Student Skill Vectors and AI results.
- Persisted recommendations, matches and auditable result metadata.

### Python owns computation and derived technical artifacts

- Transcript and syllabus extraction.
- Canonical skill-vector calculation and recalculation.
- Skill-gap calculation.
- Grounded course retrieval/ranking.
- Quiz generation and structural validation.
- Job matching and, only if approved, mentor matching.
- Taxonomy/catalog indexes, embeddings, model configuration and provider fallback.
- Ephemeral request processing state.

### Python state boundary

Python may persist derived indexes, cache entries and durable async-operation state, but it is not the system of record for a student's transcript, profile, quiz attempt, job, mentor or approved mapping. Every derived index row must retain the authoritative opaque Java integration ID and dataset/version metadata.

## 4. Decisions required before implementation

The implementation cannot begin with OpenAPI until these decisions are approved and recorded in `docs/adr/`.

| ADR | Decision | Recommended default | Approval consequence |
|---|---|---|---|
| ADR-001 | Service and data ownership | Ownership model in section 3 | Defines persistence and synchronization boundaries |
| ADR-002 | Wire naming and base path | JSON uses `snake_case`; base path `/api/v1`; Java maps at its adapter | Prevents Python DTOs leaking into Java domain code |
| ADR-003 | Canonical identifiers | Opaque string integration IDs; qualified course code; canonical skill ID; immutable career-path code | Drives migrations and every schema |
| ADR-004 | Proficiency and enums | `0.0..1.0`; `strong/moderate/weak`; percentage only at UI edge | Prevents scale and case bugs |
| ADR-005 | Student Skill Vector | Versioned document computed only by Python and stored/version-referenced by Java | Prevents duplicate computation |
| ADR-006 | Synchronous versus asynchronous work | Transcript/vector/gap/recommendation/quiz/job scoring synchronous only when budgets are proven; syllabus extraction uses `202 + operation` | Aligns contract with NFR-PERF-08 |
| ADR-007 | Error, retry and idempotency semantics | RFC 9457; correlation ID always; idempotency key only for accepted/side-effecting operations | Makes retries safe |
| ADR-008 | Service authentication | Bearer service token locally/in first deployment; TLS and network policy in production; mTLS may replace token later | Defines headers and configuration |
| ADR-009 | Mentor scope | **DECIDED 24 Aug 2026: defer AI ranking.** Existing list/booking remains required and unchanged | Mentor ranking excluded from v1 contract and gates |
| ADR-010 | Cross-runtime test harness | Managed FastAPI subprocess for local/CI baseline; Docker/Testcontainers optional when available | Makes real E2E executable |
| ADR-011 | Migration framework | Adopt Flyway for Java/MySQL/H2-compatible migrations and stop relying on `ddl-auto=update` | Makes schema changes repeatable |

### Requirement ambiguity requiring human approval

Canonical `Combined_requirements.txt` requires viewing mentors and booking consultations. The AI pipeline and NFRs describe AI-ranked mentor matching with explanations. Until the supervisor/product owner approves the stronger interpretation, mentor ranking is a separate optional milestone; current secure list/booking behavior must not be removed.

## 5. Canonical domain model

### 5.1 Cross-service identifiers

No Java database identity column is sent as a cross-service identity.

| Concept | Canonical wire identity | Notes |
|---|---|---|
| Student/candidate | `student_id` opaque string, preferably UUID | Java creates and owns it |
| Job | `job_id` opaque string, preferably UUID | Java creates and owns it |
| Mentor | `mentor_id` opaque string, preferably UUID | Java creates and owns it |
| Career path | immutable `career_path_code` | Separate `career_path_name` is display text |
| Course | `institution_code + catalog_version + course_code` | `course_code` remains mandatory; current MEU deployment can use one institution value |
| Skill | canonical string `skill_id` | `skill_label` is display text and may change |
| AI operation | `operation_id` opaque string | Used for async polling/cancellation |
| Skill vector | `vector_version` opaque/version string | Identifies one exact computed artifact |

### 5.2 Score and classification rules

- Proficiency, coverage, gaps, readiness and relevance use decimal `0.0..1.0` on the internal API.
- Java converts to `0..100` only in presentation mapping where the public API/UI still expects percentages.
- Wire classifications use the enum `strong`, `moderate`, `weak`.
- Thresholds and scoring formulas are versioned and must not be duplicated in Java.
- Java validates every numeric range before persistence.

### 5.3 Canonical Student Skill Vector

The OpenAPI schema should model a document equivalent to:

```json
{
  "student_id": "stu_8ad8...",
  "career_path_code": "backend-engineering",
  "vector_version": "vec_2026_08_23_001",
  "taxonomy_version": "taxonomy-1.0",
  "course_map_version": "meu-2026.1",
  "scoring_version": "score-1.0",
  "source": "grades+quizzes",
  "skills": [
    {
      "skill_id": "custom:python",
      "skill_label": "Python programming",
      "proficiency": 0.82,
      "coverage": 0.75,
      "evidence": [
        {
          "institution_code": "MEU",
          "catalog_version": "2026",
          "course_code": "0412201",
          "grade": "B",
          "normalized_grade": 0.75
        }
      ],
      "quiz_evidence": {
        "quiz_id": "quiz_...",
        "score": 0.9
      }
    }
  ]
}
```

Java submits confirmed courses and quiz evidence. Python computes the vector and returns a new version. M3, M4 and M6 consume this exact document or its immutable version reference; they do not independently rebuild a different vector from a reduced payload.

## 6. Proposed internal API surface

The exact paths and schemas are frozen only after ADR approval. The recommended v1 surface is:

| Method and path | Purpose | Execution model |
|---|---|---|
| `POST /api/v1/transcripts/parse` | Parse a transcript PDF and return review rows | Multipart, synchronous within 30-second budget |
| `POST /api/v1/skill-vector` | Compute/recompute a versioned vector from confirmed courses and quiz evidence | JSON, synchronous within 10-second budget |
| `POST /api/v1/skill-gap` | Compare one supplied vector with one career-path requirement version | JSON, synchronous within 10-second budget |
| `POST /api/v1/recommendations` | Return grounded ranked courses for supplied gaps/vector | JSON, synchronous within 5-second target |
| `POST /api/v1/quizzes` | Generate a validated quiz for canonical `skill_id` | JSON, synchronous within 15-second budget |
| ~~`POST /api/v1/job-matches/jobs`~~ | ~~Rank supplied Java-owned jobs for one vector~~ | **DESCOPED — not in v1** |
| ~~`POST /api/v1/job-matches/candidates`~~ | ~~Rank supplied candidate vectors for one job~~ | **DESCOPED — not in v1** |
| `POST /api/v1/syllabi/preview` | Fast parse/preview before approval | Multipart, synchronous |
| `POST /api/v1/extractions` | Submit full syllabus/course-skill extraction | Multipart, `202 Accepted` operation resource |
| `GET /api/v1/extractions/{operation_id}` | Poll durable extraction status/result | JSON |
| `DELETE /api/v1/extractions/{operation_id}` | Cancel when allowed | Idempotent cancellation semantics |
| ~~`POST /api/v1/mentor-matches`~~ | ~~Rank supplied mentors~~ | **DESCOPED — ADR-009 resolved: defer** |

The authoritative file will be `docs/contracts/careercompass-ai-internal-v1.yaml`. The existing `docs/contracts/AI_SERVICE_CONTRACT.docx` remains historical and must be marked superseded after contract approval, not silently deleted.

### Required shared schemas

- `ProblemDetails` compatible with RFC 9457.
- `CorrelationHeaders` and operation-specific idempotency rules.
- Qualified `CourseIdentity` and `ConfirmedCourse`.
- `TranscriptParseRequest` multipart definition and `TranscriptParseResponse` with confidence/warnings.
- `SkillVectorRequest` and versioned `SkillVectorDocument`.
- `SkillGapRequest`, `SkillGapItem` and `SkillGapResponse` with readiness.
- `RecommendationRequest`, ranked recommendation item, coverage and unserved skills.
- `QuizRequest`, option objects with stable option IDs, questions and server-only answer key.
- Student-to-jobs and job-to-candidates batch requests/responses.
- Syllabus preview/extraction operation and proposed mapping schemas.
- Mentor schemas only if ADR-009 is approved.

Every response field must be classified in the contract as one of:

- required and persisted by Java;
- required and exposed through Java's public API;
- required for audit/observability;
- optional provider/diagnostic metadata.

The anti-corruption adapter may omit optional provider metadata from domain objects, but it must not silently discard required contract data.

## 7. Database and backward-compatible migration plan

The current backend has no migration framework, uses `ddl-auto=update` in development, and `validate` in production. Before entity changes:

1. Adopt Flyway and baseline the existing schema through an operator-reviewed process.
2. Keep all first-release migrations additive and nullable where legacy rows cannot be resolved safely.
3. Use dual-read/dual-write during transition.
4. Add validation and non-null/unique constraints only after backfill reports are clean.
5. Do not remove the legacy numeric primary keys or display-name fields in this project increment.

### Proposed additive fields/tables

- `academic_records`: qualified `course_code`, institution/catalog fields, mapping status and correction provenance.
- `career_paths`: unique immutable `career_path_code`, ontology version.
- `skills`: unique canonical `external_skill_id`; keep `skill_name` as label.
- `job_seekers`, `jobs`, and `experts`: unique opaque integration/public IDs.
- `quizzes`: canonical `skill_id`, optional qualified course context, vector version used to generate it.
- `jobseeker_skills`: vector version and normalized proficiency semantics, or a documented current-projection mapping.
- A versioned skill-vector store, preferably a hybrid: immutable validated JSON document plus normalized current projection for queries.
- An AI operation/result audit table with operation, correlation ID, contract version, latency/status and result reference; never store raw secrets or unnecessary transcript content.

### Legacy-data strategy

- Generate new opaque UUIDs for Java-owned people/jobs/mentors; this is not an ambiguous semantic backfill.
- Do not infer course codes from course names automatically. Mark legacy records `unresolved` and provide a reviewed mapping/backfill report.
- Do not infer canonical skill IDs from labels without an approved taxonomy mapping. Mark unresolved skills explicitly.
- Generate career-path codes from an approved mapping, not an unchecked title slug; codes become immutable after publication.
- Legacy quizzes without `skill_id` remain readable but cannot update a skill until reviewed/backfilled.
- Keep a rollback path that disables the real integration profile without reversing additive migrations.

## 8. Delivery milestones

Each milestone is independently reviewable. Do not begin the next vertical capability until the current exit gate passes.

| Milestone | Deliverable | Depends on | Exit gate |
|---|---|---|---|
| M0 | Baseline, traceability and ADR approvals | None | Decisions and scope approved |
| M1 | Canonical OpenAPI and shared fixtures | M0 | Spec validation and examples pass |
| M2 | Additive migrations and adapter scaffolding | M1 | Migration/backfill tests pass |
| M3 | Transcript → confirmed courses vertical slice | M2 | Course code survives real HTTP and persistence |
| M4 | Skill vector → gap vertical slice | M3 | One vector version used end-to-end; scale tests pass |
| M5 | Recommendations | M4 | Grounded ranked response maps without lost required fields |
| M6 | Quiz generation and skill-ID write-back | M4 | Grade evidence produces a new Python vector version |
| ~~M7~~ | ~~Online job matching in both directions~~ | — | **DESCOPED for this release** (owner decision, 24 Aug 2026) |
| M8 | Syllabus/learning-outcome review flow | M2 | Proposed mapping is never authoritative before approval |
| ~~M9~~ | ~~Mentor ranking, only if approved~~ | — | **DESCOPED for this release** (ADR-009 resolved: defer) |
| M10 | Resilience, security and observability hardening | M3–M9 | Failure and security tests pass |
| M11 | Cross-runtime E2E, performance and rollout | All required milestones | All mandatory acceptance gates pass |

## 9. Detailed implementation sequence

### M0 — Preflight and ADRs

**Work**

- Record current branches, commit, staged changes and test baselines.
- Reconfirm entity/repository/controller boundaries and Python module entry points.
- Trace each proposed operation to FR-JS, FR-AI and NFR requirements.
- Approve ADR-001 through ADR-011.
- Mark mentor ranking as required or deferred.
- Define the exact course institution/catalog identity for current data.

**Tests/evidence**

- Existing Java/Python suites recorded without source changes.
- Current OpenAPI route inventory and six failing legacy probes preserved as regression evidence.

**Exit gate**

- No unresolved decision affects contract schema or migrations.

### M1 — Canonical OpenAPI contract

**Work**

- Create `docs/contracts/careercompass-ai-internal-v1.yaml` using OpenAPI 3.x.
- Define paths, content types, constraints, examples, response codes, security scheme, timeouts in descriptions, correlation header and idempotency rules.
- Define RFC 9457 errors for `400`, `404`, `409`, `413`, `422`, `429`, `500`, `502`, `503` and `504` where applicable.
- Add valid and invalid shared JSON/multipart fixtures.
- State explicitly: `Java public API != Python internal API`.
- Mark the DOCX contract historical/superseded only after approval.

**Tests/evidence**

- OpenAPI validator/linter passes.
- Every example validates against its schema.
- A compatibility policy defines additive versus breaking changes.

**Rollback**

- Documentation-only until approved; no runtime behavior changes.

### M2 — Migrations and adapter scaffolding

**Work**

- Introduce Flyway and a controlled baseline.
- Add opaque IDs, course/career/skill identities, vector metadata and quiz skill references additively.
- Add Java transport-only request/response records separate from domain/public DTOs.
- Add explicit mappers and boundary validators.
- Add Python v1 schemas alongside existing schemas where additive compatibility is needed.

**Tests/evidence**

- Fresh H2/MySQL-compatible schema migration tests.
- Upgrade test from a copy of the current schema.
- Unresolved legacy rows are reported, never guessed.
- Mapper tests cover snake_case, enum normalization and `0..1 ↔ UI percent` conversion.

**Rollback**

- Additive schema remains safe; feature stays disabled.

### M3 — Transcript vertical slice

**Work**

- Make Java send multipart PDF to `/api/v1/transcripts/parse` through the integration adapter.
- Add service authentication/correlation headers without sending transcript bytes to logs.
- Make Python return typed course rows with qualified code, name, grade, confidence, low-confidence flag and warnings.
- Preserve the code through extraction review, correction, confirmation, `AcademicRecord` and vector request.
- Keep Java confirmation-before-persistence behavior.

**Tests/evidence**

- Python route tests: valid PDF, wrong type, oversized, unparseable and low-confidence cases.
- Java HTTP contract tests inspect actual multipart parts and deserialize the canonical response.
- Java service test proves corrected `course_code` persists.
- Real FastAPI subprocess test proves a valid Java upload is not `404` or contract-mismatch `422`.

**Exit gate**

- A course code survives upload → review → correction → confirmation → database.

### M4 — Skill vector and gap vertical slice

**Work**

- Send confirmed qualified courses and quiz evidence to Python.
- Return the versioned vector with canonical skill IDs, `0..1` proficiency, coverage and evidence.
- Persist the vector document/version and update Java's current projection explicitly.
- Make skill gap consume that vector, not a reduced name/score list and not a separately recomputed transcript representation.
- Return canonical lower-case classes, targets, current values, gaps, readiness and explanations/evidence.

**Tests/evidence**

- Conversion tests prove `0.82` is displayed as `82%`, never `0.82%` or `82.0` at the wrong boundary.
- Same vector version reaches M3.
- Unknown career-path code and taxonomy-version mismatch return controlled problems.
- Many courses to one skill and one course to many skills are tested.

**Exit gate**

- Java persists and displays one Python-computed, versioned vector and its corresponding gap.

### M5 — Recommendations

**Work**

- Send the canonical vector/gap and approved filters.
- Preserve course ID, title, provider, URL, relevance, rank, target/unserved skills, coverage and explanation.
- Enforce configurable relevance threshold and grounded-catalog membership.
- Map required fields through Java persistence and public API deliberately.

**Tests/evidence**

- Empty catalog is distinct from no gaps.
- Invalid/dead/missing course identity is rejected at the boundary.
- Ranking, threshold and `skills_without_courses` behavior are tested.

### M6 — Quiz generation and write-back

**Work**

- Request quizzes by canonical `skill_id`, with optional qualified course context.
- Use stable option IDs in an options array; contract guarantees exactly one correct option ID.
- Java stores the protected answer key and remains responsible for grading.
- Persist attempts against `skill_id` and vector version.
- Send graded quiz evidence to Python; Python computes and returns a new vector version.
- Remove all `courseName == skillName` logic.

**Tests/evidence**

- Requested count bounds and exactly-one-answer validation.
- Invalid answer ID and malformed answer key produce a controlled dependency error.
- Many-to-many ontology test proves only the assessed canonical skill receives quiz evidence.
- Full quiz submit produces a new vector version and refreshed gap.

### M7 — Job matching

**Work**

- Reuse Python job-term normalization and real job/career requirements.
- Implement deterministic, explainable batch scoring for student-to-jobs and job-to-candidates.
- Java sends only the candidate vectors/jobs needed for the request, identified by Java-owned opaque IDs.
- Return score, matched skills, missing skills, explanation, confidence/version metadata and stable ordering.
- Java applies authorization and persists match projections/results.
- Replace sequential one-HTTP-call-per-item loops with bounded batches.

**Tests/evidence**

- Symmetric fixtures verify both directions use the same scoring semantics.
- Scores are deterministic and bounded `0..1`.
- No invented job or candidate ID can appear.
- Threshold, tie ordering, empty input, oversized batch and unknown skill tests.
- Job Seeker and Employer Java E2E flows persist and return correct IDs/scores.

### M8 — Learning outcomes and syllabus extraction

**Work**

- Add `DataAnalysisClient` operations for preview, async submit, poll and cancel.
- Java uploads the syllabus/learning-outcome PDF; Python returns a proposed mapping with confidence/evidence.
- Java exposes review/approval and persists only approved mappings.
- Approved changes publish a new `course_map_version`; Python rebuilds/updates derived indexes against that version.
- Replace Python's in-process operation store before multi-instance production, or explicitly restrict the first release to one instance.

**Tests/evidence**

- `202 + operation_id + Location` and polling contract.
- Duplicate/idempotent submission, cancel conflict, restart/durability and failure tests.
- Rejected mappings never enter the approved Java store or production index.

### M9 — Mentor scope

If ADR-009 defers AI ranking:

- Retain secure Java list/booking behavior.
- Document that Module 6 v1 contains job matching only.
- Do not claim mentor AI requirements are implemented.

If ADR-009 requires AI ranking:

- Add canonical mentor expertise/vector representation and `/api/v1/mentor-matches`.
- Java supplies only authorized active mentors with opaque IDs.
- Python returns grounded ranked IDs, score, aligned/missing skills and explanation.
- Consultation booking remains entirely in Java.

### M10 — Transport resilience, security and observability

**Work**

- Configure per-operation deadlines: transcript 30 seconds, vector/gap 10 seconds, quiz 15 seconds, recommendations/job retrieval 5 seconds, subject to measured budgets.
- Keep long operations asynchronous rather than increasing synchronous timeouts indefinitely.
- Decode `application/problem+json` and map dependency failures to controlled Java application errors.
- Retry only explicitly idempotent transient failures (`502/503/504`, connection reset) with bounded exponential backoff and jitter; never retry `4xx` validation errors.
- Add circuit breaker/bulkhead only after selecting a supported dependency and testing state transitions.
- Send one canonical `X-Correlation-ID`; use `Idempotency-Key` only where the contract defines it.
- Support `AI_SERVICE_BASE_URL`, `AI_SERVICE_TOKEN` and operation timeout configuration through environment/configuration.
- Use TLS and network policy in production; allow documented HTTP localhost mode for integration tests.
- Add rate limits for LLM-backed routes.
- Log operation, correlation ID, latency, status, retry count and provider/fallback metadata without logging transcript contents, answer keys, tokens or unnecessary personal data.

**Tests/evidence**

- Error/status mapping, no-retry/retry, timeout, circuit state and redaction tests.
- Missing/invalid service token tests.
- Correlation ID propagates Java → Python → logs/problem response.

### M11 — Profiles, E2E, performance and rollout

**Runtime profiles**

- `application-dev.yml`: mock allowed and explicit.
- `application-test.yml`: mock allowed for isolated Java unit tests.
- `application-integration.yml`: `use-mock=false`, local service URL/token, real HTTP.
- `application-prod.yml`: `use-mock=false`; startup fails if URL/token/security configuration is absent.
- Base configuration must not silently make production use a mock.
- Startup/health diagnostics expose mode and AI readiness without exposing secrets.

**Cross-runtime harness**

1. Create isolated test data/temp directories and select a free port.
2. Start the real FastAPI app as a managed Python subprocess with deterministic taxonomy/catalog fixtures and a deterministic test LLM gateway.
3. Poll `/api/v1/health/ready` with a bounded startup deadline.
4. Run Java Maven Failsafe tests with the integration profile and `use-mock=false`.
5. Capture sanitized Java/Python logs on failure.
6. Stop the Python process and clean temporary state reliably.

This uses the real HTTP stack, routes, validation and algorithms. The deterministic LLM provider makes CI repeatable; a separate opt-in smoke test checks a configured live provider and must not be required for every commit.

**Required E2E journeys**

- Transcript upload → review/correct → confirm/persist → vector → gap → recommendations → quiz → submit/grade → quiz evidence → new vector version → refreshed gap.
- Student vector → supplied jobs → Python batch match → Java persistence → public Java response.
- Job → supplied candidate vectors → Python batch match → Java persistence → Employer response.
- Learning-outcome upload → preview/submit → proposed mapping → Java review/approval → versioned approved map/index.
- Mentor ranking only if ADR-009 approves it.

**Performance and failure gates**

- Measure each NFR latency budget at p95 under the documented test load.
- Exercise provider outage, Python unavailable, timeout, malformed response, stale taxonomy version and durable-job restart.
- Verify 100-active-user target with realistic batch sizes before production sign-off.

## 10. Testing matrix

| Layer | Required coverage |
|---|---|
| OpenAPI | Spec lint/validation, examples, breaking-change check |
| Python unit | Vector/gap/recommendation/quiz/job scoring, identifiers, ranges and determinism |
| Python API | Every route: valid, invalid, auth, dependency error and content type |
| Java mapper | Every field, enum, range, snake_case mapping and percentage conversion |
| Java HTTP client | Actual multipart/JSON serialization, response parsing, RFC 9457 errors, retries and timeouts |
| Java service | Persistence, authorization, confirmation, write-back and stale-data replacement |
| Migration | Fresh schema, upgrade, backfill, unresolved records and constraints |
| Cross-runtime contract | Real Java-produced request accepted by real FastAPI; real response accepted by Java |
| E2E | Full student, job-seeker, employer and learning-outcome journeys |
| Optional live AI | Provider connectivity/quality smoke test, separated from deterministic CI |

No service is declared integrated merely because its isolated unit tests pass.

## 11. Acceptance criteria

### Contract and endpoint compatibility

- All **approved** v1 endpoints exist and valid Java operations do not receive `404`.
- Every valid canonical Java fixture passes Python validation without a contract-mismatch `422`.
- Invalid fixtures return the documented controlled `4xx` problem response.
- Java validates and deserializes every required Python response field.

### Identifier and vector compatibility

- Qualified course codes survive extraction, review, correction, persistence and vector calculation.
- Canonical skill IDs are used throughout; display labels are never identity.
- Career paths use immutable cross-service codes.
- People, jobs and mentors use opaque Java-owned integration IDs, not database-local integers.
- Internal numeric scores use `0.0..1.0`; UI percentage conversion is tested.
- Python alone computes versioned vectors; all downstream results reference the correct vector/data versions.

### Functional compatibility

- Transcript, vector, gap, recommendations, quiz and both job-match directions pass real HTTP tests.
- Quiz write-back uses `skill_id` and produces a new vector version.
- Syllabus integration follows preview/propose/review/approve semantics.
- Mentor behavior matches the approved ADR-009 scope and is described honestly.

### Runtime, errors and security

- Integration and production run with `use-mock=false` and cannot silently fall back.
- Controlled problems replace raw WebClient, null-pointer and serialization failures.
- Retries are bounded and idempotency-safe.
- Operation timeouts/async flows satisfy the approved NFR interpretation.
- Service authentication, production TLS/network controls, rate limiting, correlation and safe logs are configured.

### Build and E2E

- Java compiles and all Java tests pass.
- Python tests and API tests pass.
- OpenAPI validation and compatibility checks pass.
- Cross-runtime E2E passes with the real FastAPI process and `use-mock=false`.
- If the environment lacks `javac`, cannot start FastAPI, or cannot run the E2E harness, the integration remains **blocked**, not complete.

## 12. Rollout and rollback strategy

1. Add v1 endpoints and migrations without removing existing Python routes or Java mock support.
2. Keep real mode disabled in normal development until M3/M4 contract tests pass.
3. Enable capabilities incrementally in the integration profile: transcript → vector/gap → recommendations → quiz → jobs → syllabus.
4. Run shadow comparisons where safe, recording only non-sensitive metrics; do not persist mock results as real AI results.
5. Promote `use-mock=false` to production only after M11 sign-off.
6. Operational rollback switches the deployment back to the last verified service version; additive migrations remain compatible. Production must fail clearly rather than automatically fall back to mock behavior.
7. Remove deprecated endpoints/legacy fields only in a later explicitly approved release after usage and backfill checks.

## 13. Risks and controls

| Risk | Control |
|---|---|
| Big-bang change breaks working Java behavior | Vertical milestones, additive routes/migrations and per-capability gates |
| Existing names cannot be mapped to codes/IDs | Explicit unresolved status and reviewed backfill; no guessing |
| Python and Java calculate different vectors | Python-only computation and immutable vector versions |
| External LLM makes CI flaky | Deterministic test gateway plus separate live-provider smoke test |
| Async jobs disappear on restart | Durable operation store before multi-instance production |
| Job matching exceeds 5 seconds | Batch contract, bounded input, local deterministic scoring, profiling |
| Sensitive data enters logs | Structured redaction tests and metadata-only observability |
| Contract drifts again | OpenAPI source of truth, fixtures, CI conformance and breaking-change check |
| Optional mentor scope blocks core release | ADR-009 gate and separate milestone |
| Migration damages legacy data | Additive schema, backups, dry-run reports and delayed constraints |

## 14. Required implementation completion report

When this plan is executed, the final implementation report must include:

1. Files changed.
2. Migrations added and backfill results.
3. OpenAPI endpoints/schemas implemented or changed.
4. Canonical identifier and score decisions.
5. Java adapter and domain/persistence changes.
6. Python route, schema and algorithm changes.
7. Job and mentor status.
8. Syllabus/learning-outcome status.
9. Tests added.
10. Exact commands executed.
11. Exact test results.
12. Remaining blockers.
13. Human-approved assumptions/ADRs.
14. Evidence that integration/production do not silently use mocks.

Do not claim success while any mandatory acceptance gate is unverified.

## 15. Immediate next action

*(Superseded — the ADRs were approved and implementation has begun. See §16 and §17.)*

The ADRs were recorded in `docs/adr/` as ADR-001 … ADR-007, consolidating the eleven decisions
listed in §4. With those approved, M1 created the authoritative OpenAPI file and the first
vertical slices followed. The next action is now the remaining work listed in §17.

## 16. Implementation status — 24 August 2026

Job matching (M7) and mentor AI ranking (M9) are **descoped for this release**; they are excluded
from the gates below rather than counted as failures.

### Delivered and verified

| Milestone | State | Evidence |
|---|---|---|
| M0 — ADRs and baseline | **Done** | `docs/adr/ADR-001…007`; test baselines recorded before any change |
| M1 — Canonical OpenAPI | **Done** | `docs/contracts/careercompass-ai-internal-v1.yaml` — 7 paths, 21 schemas, passes `openapi-spec-validator` |
| M2 — Adapter scaffolding | **Partial** | `AiWire` transport records + mappers done; migrations written by hand, Flyway not yet wired (see §17) |
| M3 — Transcript slice | **Done** | Multipart upload to `/api/v1/transcripts/parse`; course code survives to `AcademicRecord` |
| M4 — Vector and gap | **Done** | Both routed, mapped and covered by contract and live tests |
| M5 — Recommendations | **Done** | Grounded catalog items with links, relevance and targeted skill id |
| M6 — Quiz and write-back | **Done** | Quizzes keyed by `skill_id`; graded evidence returned to the AI service, which recomputes the vector |
| M10 — Resilience/security | **Partial** | Per-operation deadlines, RFC 9457 decoding, correlation id, bearer token, profile hardening done; retries, circuit breaker, TLS and rate limiting not done |
| M11 — Cross-runtime E2E | **Partial** | Live contract suite passes against the real service; the full student journey over real HTTP is not yet automated |

### The compatibility blockers from the audit

| Audit blocker | State |
|---|---|
| All six Java paths return `404` | **Resolved** for the five in-scope operations. Job matching returns a controlled "not in this release" error instead of calling a path that does not exist |
| Java payloads rejected with `422` | **Resolved** — verified against the running service, not against a fixture |
| Score scale conflict (`0..1` vs `0..100`) | **Resolved** — converted once, at the adapter; out-of-range values are rejected rather than persisted |
| Classification case conflict | **Resolved** — normalised at the adapter; comparisons are case-insensitive |
| Course identity lost in Java | **Resolved** — `course_code` carried end to end; a course without one is reported, never silently dropped |
| Career path identity conflict | **Resolved for v1** — the path's name is sent; an unknown name surfaces the names the service knows |
| Quiz write-back keyed on course name | **Resolved** — keyed on canonical `skill_id`; quizzes without one are skipped, not guessed at |
| No shared error mapping | **Resolved** — RFC 9457 decoded into `AiServiceException` (502/503/504) |
| Mock is the runtime default | **Resolved** — `integration` and `prod` profiles pin `use-mock=false`; prod fails to start without a URL and token |
| No real contract or E2E test | **Resolved** — 17 new HTTP-level tests, 6 of them against the running service |
| Job matching missing in Python | **Descoped**, by owner decision |
| Mentor AI matching missing | **Descoped**, per ADR-005 |
| Learning-outcome ingestion disconnected | **Open** — M8 not started |

### Verification actually performed

Toolchain note: the machine had a JRE but no `javac`, so nothing Java could be compiled or run.
A user-local JDK 17 was installed at `~/.local/lib/jvm/jdk-17.0.20.1+1` (no root; matches the
project's `java.version` and Lombok 1.18.34, which does not support the installed JDK 25).
The Python environment was also empty and was restored with `uv sync`.

```text
Java   mvn -o test            185 run, 10 failures, 18 errors, 6 skipped
                              -> identical to the pre-existing baseline of
                                 167 run / 10 failures / 18 errors.
                                 18 net new tests, 0 new failures.
                                 The 6 skipped are the live tests, which
                                 skip unless -Dcc.ai.base-url is supplied.

Live   mvn -o test -Dtest=HttpDataAnalysisClientLiveContractTest \
           -Dcc.ai.base-url=http://127.0.0.1:8123
                              6 run, 0 failures  <- against the real FastAPI
                              service, including a real LLM-generated quiz

Python uv run --extra dev pytest -q
                              128 passed, 5 errors
                              -> unchanged; the 5 are pre-existing collection
                                 errors in tests/test_skill_matcher.py, which
                                 is a script-style suite with its own main()
                                 and is not pytest-compatible.

Spec   openapi-spec-validator  VALID (7 paths, 21 schemas)
```

The pre-existing Java failures are **not** in the AI integration. They are merge fallout in the
`Backend` branch: `TokenRevocationService` is missing from the `@WebMvcTest` slices
(`AuthControllerTest`, `SecurityIntegrationTest`), `GlobalExceptionHandlerTest` receives 403
where it expects 4xx, plus one Mockito strict-stub error and one job-match test NPE. They were
deliberately left alone — fixing them is separate work, and folding it in here would have made
this change impossible to review.

## 17. Remaining work

Nothing below is blocked; none of it is done.

1. **Flyway is not wired in** (ADR-007). Migrations exist as SQL under `backend/db/migrations/`
   and follow the established naming, but `ddl-auto` still creates the schema in dev.
   `quizzes.skill_id` and `academic_records.course_code` must be applied by migration before any
   environment running `ddl-auto: validate` — production will otherwise fail to start.
2. **`vector_version` is not implemented** (ADR-003). The AI service returns `taxonomy_version`
   but no document identity, so downstream operations recompute the vector from the same courses
   rather than referencing one stored artefact. The recomputation is deterministic, so results
   agree today — but nothing enforces it, and the `409` on version mismatch that ADR-003 requires
   cannot be raised yet.
3. **Opaque cross-service ids** are not introduced. No v1 operation is student-scoped, so nothing
   currently needs them; they become necessary with job matching.
4. **M8 — learning outcomes** is untouched. `DataAnalysisClient` still has no syllabus operation,
   so Java's uploaded PDFs remain disconnected from the AI service's extraction.
5. **Retries, circuit breaker, TLS, rate limiting** are not implemented. Deadlines and error
   mapping are, so failures are already controlled — but a transient blip is not retried.
6. **The full journey is not automated end to end.** The live suite proves each operation over
   real HTTP; upload → confirm → dashboard → recommend → quiz → submit → refreshed dashboard is
   still only covered against mocks.
7. **`career_path_code`** is deferred. Administrators can still create a career path whose name
   the AI service does not know; that now fails with a message listing the valid names, rather
   than silently returning nothing, but it is a runtime failure rather than a constraint.
8. **The pre-existing test failures** listed in §16 remain.
