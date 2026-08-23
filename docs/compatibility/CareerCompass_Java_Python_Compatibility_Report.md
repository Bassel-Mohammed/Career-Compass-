# CareerCompass Java–Python Compatibility Audit

**Audit date:** 23 August 2026  
**Repository:** `Bassel-Mohammed/Career-Compass-` merged workspace  
**Branch:** `integration/full-stack`  
**Commit inspected:** `042724a38872e51bfc247b01fe3b38a23a9b99c0`  
**Planning baseline:** `/home/almadhoun/Desktop/CareerCompass`  
**Decision:** **NOT COMPATIBLE for real end-to-end operation** *(as of the commit inspected — see status update)*

> **Status update — 24 August 2026.** This audit records the state at commit `042724a`.
> Remediation has since begun in the working tree, so parts of this document are now out of
> date. Superseded findings are marked **[SUPERSEDED]** or **[RESOLVED]** inline. Live
> per-milestone status is tracked in `JAVA_PYTHON_INTEGRATION_FIX_PLAN.md` §16.
>
> **Scope decision:** job matching (M7) and mentor AI ranking (M9) are descoped for the
> current release by owner decision. The blockers this audit raises against them therefore
> remain open **by design, not by oversight**, and are excluded from the acceptance gates
> in §10 for this release.

## 1. Executive decision

The Java backend and Python AI service cannot currently exchange the data required by the CareerCompass functional requirements. The Java business services are wired cleanly to a six-operation `DataAnalysisClient`, and Python implements useful AI logic for five of those six capabilities, but their HTTP contracts were developed independently.

The result is definitive:

- **0 of the 6 paths called by Java exist in FastAPI.** In-process HTTP probes returned `404` for every Java path. **[SUPERSEDED 24 Aug 2026 — transcript extraction now calls `POST /api/v1/transcripts/parse` and is aligned; the other 5 paths still return `404`.]**
- If Java is redirected to Python's nearest native routes, **all 5 available capabilities reject Java's current payloads with `422`** before any AI logic runs.
- **5 of 6 underlying capabilities exist in Python** in some form: transcript parsing, skill vector, skill gap, course recommendation, and quiz generation.
- **Job matching is not exposed or implemented as an online student/job scorer.** Python's Module 6 status is “not started,” and no mentor-matching capability exists.
- Java uses `MockDataAnalysisClient` by default, so the application currently **does not call Python at all** unless `careercompass.ai-service.use-mock=false` is supplied.
- The repository contains unit and service tests for each side, but **no real Java ↔ FastAPI contract or end-to-end HTTP test**.

This means a UI can be developed against the Java public endpoints and mock behavior, but it would be unsafe to treat the AI-backed functional requirements as integrated or complete. The contract and identifier model should be fixed before UI behavior is finalized around response details.

## 2. Scope and evidence

This audit compared four kinds of evidence:

1. The official functional and non-functional requirements in the planning directory.
2. The Java integration interface, HTTP client, DTOs, business services, persistence behavior, configuration, and tests.
3. The FastAPI route inventory, Pydantic schemas, module implementation status, error behavior, and tests.
4. Executable in-process HTTP probes against the current FastAPI application.

The requirements authority used for this report is:

1. `requirements/Combined_requirements.txt` for canonical Job Seeker requirement numbering.
2. `requirements/Non_Functional_Requirements.txt` for measurable quality constraints.
3. `planning/Section_5_3_AI_Pipeline.md` for the intended six-module processing flow.
4. `CoursesSuggestionsystem_v6.docx`, especially the internal FR-AI-01…14 interface requirements.
5. `planning/Interface_Design.md` for expected screen behavior only; its FR numbers are stale.
6. The repository contract `docs/contracts/AI_SERVICE_CONTRACT.docx`, which accurately describes Java's current DTOs but does not describe Python's implemented API.

## 3. Compatibility scorecard

| Area | Result | Evidence and consequence |
|---|---|---|
| Java integration abstraction | Good foundation | One interface isolates the business layer from transport and supports mock/HTTP implementations. |
| Exact endpoint compatibility | **Fail — blocker** | All six Java paths return `404` from the current FastAPI app. **[SUPERSEDED — transcript now aligned; 5 of 6 still fail.]** |
| Request-schema compatibility | **Fail — blocker** | The nearest Python endpoints reject every tested Java-shaped payload with `422`. |
| Response-schema compatibility | **Fail — blocker** | Names, nesting, identifiers, score scales, enums, and required fields differ. |
| Transcript capability | **[RESOLVED at transport]** | Java now posts multipart to `/api/v1/transcripts/parse` and maps Python's canonical `courses[]` rows. Exit gate (a course code proven to survive to the database under test) is still unmet. |
| Skill vector and gap | Partial implementation | Both exist, but Java uses local numeric IDs and name/percentage pairs; Python requires course codes and canonical skill IDs with 0–1 values. |
| Course recommendation | Partial implementation | Python's grounded catalog retrieval exists, but request and nested response shapes differ and catalog coverage is incomplete. |
| Quiz generation/write-back | Partial implementation | Both sides implement useful pieces, but the transport contracts differ and Java's course-name-to-skill-name write-back is invalid for a real ontology. |
| Job matching | **Missing in Python — blocker** | Java calls one scorer per job/candidate; FastAPI has no equivalent endpoint or online M6 scoring function. |
| Mentor matching | **Missing — blocker for the planned AI module** | Java only filters stored experts by study field/status; no skill-vector score or explanation is produced. |
| Learning-outcome ingestion | **Disconnected — blocker** | Java stores uploads; Python exposes syllabus extraction; no integration method connects them. |
| Real runtime selection | **Fail — blocker** | Mock mode is the default in Java, including unless production configuration overrides it. |
| Errors, resilience, and observability | **Fail** | No shared error mapping, retry/backoff, correlation ID, boundary validation, or integration metrics. |
| Security at service boundary | **Fail for deployment** | Default plain HTTP and no service-to-service authentication or rate limiting. |
| Contract/E2E tests | **Missing** | Existing tests replace or mock the cross-service boundary. |

## 4. Endpoint-by-endpoint contract comparison

| Capability | Java currently calls | Python currently exposes | Incompatibility | Direct result |
|---|---|---|---|---|
| Transcript extraction | **[RESOLVED]** `POST /api/v1/transcripts/parse`, multipart `file` + `save=false` | `POST /api/v1/transcripts/parse`; returns canonical `courses[]` of `CanonicalTranscriptCourse` alongside the legacy `all_courses` | Aligned. Java maps snake_case at a private wire record so Python shapes do not leak into domain DTOs | Transport aligned; end-to-end test still required |
| Skill vector | `POST /skill-vector`; sends jobseeker ID, numeric career-path ID, and `{courseName,grade}`; expects `{skills:[{skillName,score 0..100}]}` | `POST /api/v1/skill-vector`; requires courses with `course_code`; returns canonical `skill_id`, label, proficiency `0..1`, coverage and evidence | Path, course identifier, identity model, score scale, naming, and response richness differ | `404`; native route: `422 body.courses.0.course_code` |
| Skill gap | `POST /skill-gap`; sends numeric `careerPathId` plus flattened vector; expects `skillGaps` and readiness percent | `POST /api/v1/skill-gap`; requires transcript courses plus exact `career_path` name and recomputes the vector; returns root `skills` and lower-case classes | Path, computation boundary, career identity, request, response, scale, enum case, and readiness differ | `404`; native route: `422 body.courses, body.career_path` |
| Course recommendations | `POST /course-recommendations`; sends numeric path ID and weak skill names; expects a bare flat array | `POST /api/v1/recommendations`; requires transcript courses and path name; returns an envelope with nested course, relevance, uncovered skills, and coverage | Path, input source, identifiers, nesting, field names, and output envelope differ | `404`; native route: `422 body.courses, body.career_path` |
| Quiz generation | `POST /quiz-generate`; sends `{courseName,questionCount}`; expects A/B/C/D fields and `correctOption` | `POST /api/v1/quizzes`; requires `{skill_id,question_count,verify}`; returns options array and separate answer key with zero-based index | Path, course-versus-skill context, naming, maximum count, and answer representation differ | `404`; native route: `422 body.skill_id` |
| Job match | `POST /job-match`; sends one skill vector and one job; expects score plus explanation | No online job-match endpoint | Capability is absent, not merely renamed | `404`; no native route exists |

### 4.1 Executable probe results

The current FastAPI app was imported from the repository using FastAPI `0.141.1` and Pydantic `2.13.4`. Its OpenAPI document contains the native routes shown above. Direct ASGI requests produced:

```text
/transcript-extract       404
/skill-vector             404
/skill-gap                404
/course-recommendations   404
/quiz-generate            404
/job-match                404
```

After mapping the first five calls to the closest Python route without changing Java bodies:

```text
/api/v1/transcripts/parse  422  invalid-request  body.file
/api/v1/skill-vector       422  invalid-request  body.courses.0.course_code
/api/v1/skill-gap          422  invalid-request  body.courses, body.career_path
/api/v1/recommendations    422  invalid-request  body.courses, body.career_path
/api/v1/quizzes            422  invalid-request  body.skill_id
```

These probes prove that changing only the base URL or route strings will not make the services compatible.

## 5. Functional-requirement traceability

| Requirement group | Intended behavior | Current evidence | End-to-end result |
|---|---|---|---|
| FR-JS-10/11, FR-AI-01/02, NFR-AI-01/02, NFR-REL-03 | Upload PDF, extract strict structured rows, flag uncertainty, let user correct, then persist | Java validates 10 MB/PDF, calls extraction, shows review, and persists after confirmation. Python parses multipart MEU plans but has no per-row low-confidence field and loosely types course rows. Contracts differ. | **Not achieved through real integration** |
| FR-JS-12/13/14, FR-AI-04…07 | Build the deterministic Student Skill Vector, compare it to a career target, classify and explain gaps, display dashboard | Java orchestrates and persists scores. Python has deterministic M2/M3. Java discards course codes, sends numeric path IDs and 0–100 name scores; Python requires course codes/path name/canonical IDs and returns 0–1 rich records. | **Components exist; integration blocked** |
| FR-JS-15/16, FR-AI-08/09, NFR-AI-04/05/08 | Return ranked, grounded catalog courses with links, target skills, scores/thresholds, and explanations | Python's M4 uses a real catalog and returns relevance and uncovered skills. Java expects a flat list without similarity values and cannot enforce a threshold. Contracts differ; real syllabus coverage is 20 of 114 courses. | **Partial capability; integration blocked** |
| FR-JS-17, FR-AI-10/11, NFR-AI-02/07 | Generate a valid skill/topic quiz with exactly one correct option | Python M5 generates, validates, and self-checks quizzes. Java validates only that the returned answer marker is A–D. Request and response shapes are incompatible. | **Capability exists; integration blocked** |
| FR-JS-18…22 | Attempt and grade deterministically, persist result, update the affected skill, use grades when no quiz exists | Java performs local grading and calls dashboard recomputation. However it stores only `courseName` and searches for a skill with the same name. A many-course-to-many-skill ontology will normally prevent the intended write-back. | **Partially implemented; write-back design must change** |
| FR-JS-23, FR-EMP-11/12, FR-AI-12/13 | Rank jobs for a seeker and candidates for an employer, with score and explanation | Java has orchestration/persistence but performs sequential per-item AI calls. Python has offline job-term extraction data, not an online profile/job matching service. | **Not achieved** |
| FR-JS-24/25, NFR-AI-04/05, Module 6 | Show appropriate mentors and support consultation booking; planning pipeline also requires AI-ranked mentor matches | Java can list active experts by study field and book consultations. It does not calculate match score or explanation. Python has no mentor catalog or matching module. | **Basic view/booking may work; planned AI matching not achieved** |
| FR-CM-04/05, FR-AI-03, NFR-MNT-03 | Upload learning outcomes, derive course-to-skill mappings, review/approve, and make them available to AI | Java stores uploaded PDFs locally and in its database. Python has preview/async syllabus extraction. `DataAnalysisClient` has no learning-outcome method and there is no synchronization contract. | **Disconnected** |
| FR-AI-14 | Store every AI response | Java stores domain results for several flows, but has no complete AI-response audit record and receives no real Python responses in default mock mode. | **Partial only** |
| NFR-MNT-01 | Six independently replaceable capabilities behind FastAPI | M1–M3 and M5 are built; M4 is partial by data coverage; M6 job/mentor is missing. | **Not met** |

## 6. Data-model blockers

### 6.1 Course identity is lost in Java — **[RESOLVED 24 Aug 2026]**

> `courseCode` is now carried through `TranscriptExtractionResponse`, `ConfirmTranscriptRequest.CourseGradeItem`, the `AcademicRecord` entity, and `CourseGradeDto` on the skill-vector request. The finding below is retained as the rationale for that change.

Python's vector builder requires `course_code` as the deterministic join key. Java's extraction review receives `courseCode`, but the confirmation request, `AcademicRecord` entity, and skill-vector request retain only course name and grade. Name-only matching is ambiguous and cannot satisfy the real course-to-skill map reliably.

**Required decision:** persist canonical course code and aliases with every academic record; do not derive integration identity from display names.

### 6.2 Skill identity and score scale conflict

Python uses canonical string `skill_id` values and proficiency in the range `0..1`. Java stores skill name and percentage-like score in `0..100`, classifying at 50 and 80. A direct deserialization would make valid Python scores appear as 0–1 percent and classify almost everything as Beginner.

**Required decision:** use canonical skill ID at the service boundary, carry a label separately, use `0..1` in the internal contract, and convert to percentage only for Java persistence/UI if needed.

### 6.3 Career-path identity conflict

Java sends a database-local integer. Python intentionally requires the career-path name and owns a separate career-path requirements artifact. Java administrators can create or rename paths without synchronizing Python, so an ID alone cannot locate the corresponding ontology.

**Required decision:** add a stable cross-service key such as `career_path_code`, plus title and `ontology_version`; define which service owns the approved career-path requirements.

### 6.4 Classification values conflict

Java depends on exact title-case values `Strong`, `Moderate`, and `Weak`; recommendation selection checks exact `Weak`. Python emits lower-case values. Without explicit mapping, Java would generate no recommendations even if the rest of the response were adapted.

### 6.5 The Student Skill Vector is not yet a shared artifact

The planning documents say every downstream module reads one versioned Student Skill Vector. Java sends a flattened vector to its gap/job operations, while Python's gap and recommendation routes recompute the vector from transcript courses. This creates duplicate computation and makes version/audit consistency difficult.

**Required decision:** define a versioned `SkillVectorDocument` containing skill ID, label, proficiency, evidence, course references, scoring version, taxonomy version, and course-map version. Either pass it downstream or identify one stored version unambiguously.

## 7. Runtime, reliability, security, and test findings

### 7.1 Runtime selection

`application.yml` sets `careercompass.ai-service.use-mock: true`. The mock returns plausible shapes but does not parse the PDF, use the real ontology/catalog, or score jobs from their requirements. This is useful for Java development, not evidence of AI functional completion.

### 7.2 Timeouts and blocking behavior

Java gives every AI call the same 30-second timeout and blocks the Spring MVC request thread. The requirements instead set approximately 30 seconds for transcripts, 10 seconds for dashboard/gap, 15 seconds for quiz generation, and 5 seconds for recommendation/job retrieval. Job matching loops over jobs or candidates and makes sequential blocking calls, so it cannot reliably meet the 5-second target or scale to 100 active users.

Python uses async job handling only for full syllabus extraction. Its in-process queue is lost on restart and therefore conflicts with the stateless FastAPI requirement. Quiz/LLM work has no FastAPI request deadline and the LLM client can wait much longer than Java's timeout.

### 7.3 Errors and response validation

Python consistently emits RFC 9457-style `application/problem+json` for its defined errors. Java's `.retrieve()` call does not decode this contract or map dependency errors to controlled `502/503/504` responses. It has no retry/backoff and assumes response lists and fields are non-null. Malformed output can therefore surface as a null-pointer or persistence error instead of a clear AI-boundary failure.

### 7.4 Security

Incoming Java user endpoints are role-protected, but outgoing calls use default `http://localhost:8000` with no API key, signed service token, or mTLS. FastAPI has no service authentication or rate limiting. CORS is not a server-to-server security control. A deployed service must use TLS, network isolation and authenticated service requests before transmitting transcripts or answer keys.

### 7.5 Observability and persistence

The requirements call for correlated logs and AI latency/provider/token monitoring. The Java integration layer sends no correlation/idempotency headers and records no per-operation transport metrics. Python has useful health routes and internal logs, but there is no shared request ID or durable audit link to Java's stored domain result.

### 7.6 Test coverage

- Python's core algorithm tests are extensive and previously completed 813 checks in this merged workspace, but they do not exercise Java DTOs.
- Java's wiring test proves only mock-versus-HTTP bean selection; it never performs a request.
- Java service and system tests mock `DataAnalysisClient`.
- No WireMock/MockWebServer serialization test exists for the real Java client.
- No shared OpenAPI conformance test or Java-to-live-FastAPI test exists.
- Java tests could not be recompiled during this audit because the machine has a Java 25 runtime and Maven but no `javac`. This does not affect the definitive path/schema probe results.

## 8. Existing strengths worth preserving

The integration should be repaired, not rewritten from scratch:

- Java has a clear integration-layer seam, keeps user authentication and domain persistence outside the AI code, validates transcript upload size/type, supports confirmation before transcript persistence, grades quizzes programmatically, and persists recommendations/job matches.
- Python has deterministic skill-vector and gap logic, a grounded course catalog with honest coverage reporting, structured quiz generation/validation, explicit problem responses, health endpoints, and a useful async pattern for expensive syllabus extraction.
- Both sides agree conceptually that Java owns user-facing orchestration and Python owns AI/data-analysis computation.

## 9. Recommended integration design

Use the Java integration layer as the anti-corruption boundary between Java domain services and the Python transport contract. Do not expose Python-specific Pydantic structures throughout Java business services, and do not make the browser call FastAPI directly.

### P0 — required before enabling real mode

1. **Freeze one versioned OpenAPI contract.** Add a source-controlled `careercompass-ai-internal-v1.yaml`; generate or validate Java transport DTOs and Python Pydantic models from it. Mark `AI_SERVICE_CONTRACT.docx` superseded after approval.
2. **Choose canonical identifiers and scales.** Preserve `course_code`; introduce stable `career_path_code`, canonical `skill_id`, explicit display labels, `0..1` proficiency, lower-case enum values, and ontology/course-map/scoring version fields.
3. **Implement Java integration adapters.** Support multipart transcript upload, map Python snake_case/envelopes to Java domain results, decode answer keys safely, and translate RFC 9457 problems to controlled backend errors.
4. **Make the vector the shared versioned artifact.** Stop relying on course name equaling skill name. Store quiz results against `skill_id`, and make M3/M4/M6 consume the same vector version.
5. **Implement Python M6 online matching.** Support both profile-to-jobs and job-to-candidates, using authoritative Java item IDs. Add mentor ranking only if the approved interpretation of FR-JS-24 includes AI matching.
6. **Connect learning outcomes.** Add a Java integration operation for syllabus/learning-outcome extraction and a review/approval flow. Java remains system of record; Python owns extraction and derived indexes.
7. **Add real HTTP contract tests.** Test every request, response, error, timeout, and content type against the actual FastAPI ASGI application and the actual Java HTTP client. Only then set `use-mock=false` in an integration profile.

### P1 — required before deployment

1. Add strict response-boundary validation and controlled `502/503/504` mappings.
2. Add operation-specific deadlines, bounded retry with exponential backoff for transient failures, a circuit breaker, and batching for job/candidate matching.
3. Add TLS, service authentication, network policy, LLM endpoint rate limiting, and secret management.
4. Add correlation and idempotency headers plus latency, provider, token, fallback, and outcome metrics.
5. Delete stale persisted skills on transcript re-upload or career-path change.
6. Implement confidence data for transcript rows and preserve correction provenance.
7. Return relevance scores and apply configurable thresholds for course/job/mentor results.
8. Replace the in-memory async queue with durable job state or explicitly limit it to single-instance development.

### P2 — documentation and quality alignment

1. Correct all FR numbering to the canonical sequence in `Combined_requirements.txt`.
2. Rewrite the technology-stack section to reflect Spring Boot + FastAPI and the actual database/index ownership.
3. Resolve Strong/Moderate/Weak thresholds and whether gaps are course-grade or career-target based.
4. Clarify whether FR-JS-24 is simple mentor viewing or AI-ranked mentor matching.
5. Run performance, extraction-accuracy, failure/fallback, security, and 100-user load tests against the integrated deployment.

## 10. Acceptance gates for compatibility

The services should be declared compatible only when all of these pass:

- Every approved internal endpoint is present under one versioned base path and returns no `404` for a valid operation.
- Java-produced valid payloads pass Python schema validation without `422`.
- Java deserializes every valid Python response with no ignored required data and validates score ranges, enums, counts, URLs, and catalog IDs.
- Contract tests cover success plus `400`, `404`, `409`, `413`, `422`, `429`, `503`, and timeout behavior.
- A real end-to-end test completes: upload → review/correct → confirm → vector → gap/dashboard → recommendations → quiz → submit/write-back → refreshed vector.
- Real end-to-end job matching works in both seeker and employer directions; mentor matching is tested if retained in scope.
- Learning-outcome upload reaches Python extraction, returns a proposed mapping, and persists only after Java-side approval.
- Integration mode runs with `use-mock=false`; mocks remain limited to unit/local development profiles.
- Measured latency and concurrency satisfy the named NFR budgets, with fallback and retry tests proving controlled degradation.
- TLS/service authentication, rate limiting, correlated logs, and AI metrics are enabled in the deployment profile.

## 11. Document inconsistencies that must be resolved

The compatibility problem is partly caused by multiple competing specifications:

- The v6 report duplicates FR-JS-08/09, omits FR-JS-11, and shifts later IDs. `Combined_requirements.txt` has the coherent FR-JS-09…25 sequence and should become canonical everywhere.
- `Interface_Design.md` explicitly behaves as a draft and uses stale requirement IDs.
- `Section_5_5_Technology_Stack.md` describes a single Python backend with no cross-runtime bridge, while the implemented and requested architecture is Spring Boot plus FastAPI.
- Architecture/database descriptions disagree between MySQL, PostgreSQL, and SQLite. Separate Java system-of-record storage from Python knowledge-index/ephemeral processing storage explicitly.
- The Java-facing DOCX contract says all calls are unversioned synchronous JSON and asks Python to mirror Java DTOs. Python instead implements a versioned, richer API with multipart uploads and RFC 9457 errors.
- FR-AI-01…14 omit explicit transcript-extraction and mentor-matching request/response pairs even though the six-module pipeline includes both.

## 12. Final conclusion

The two codebases are **architecturally alignable but not currently interoperable**. Java's integration abstraction and Python's M1–M5 implementation provide a strong starting point. However, enabling the real HTTP client now would replace a working mock demonstration with immediate `404` errors; route-only fixes would then expose `422` validation errors and incompatible responses. Job/mentor matching and learning-outcome synchronization remain functional gaps beyond the transport mismatch.

The correct next engineering milestone is a contract-first integration increment: approve one versioned OpenAPI schema, preserve canonical IDs and score semantics, implement adapters and M6, and prove the full flow with real HTTP contract tests. UI work can proceed on layout and navigation in parallel, but AI response-dependent UI details should be based on the approved contract rather than either current implementation alone.

## Appendix A — Principal code evidence

- Java client and paths: `backend/src/main/java/com/careercompass/integration/ai/HttpDataAnalysisClient.java:38–83`
- Java interface: `backend/src/main/java/com/careercompass/integration/ai/DataAnalysisClient.java:25–43`
- Java runtime configuration: `backend/src/main/resources/application.yml:31–36`
- Transcript orchestration/persistence: `backend/src/main/java/com/careercompass/service/TranscriptService.java:61–223`
- Recommendation orchestration: `backend/src/main/java/com/careercompass/service/CourseRecommendationService.java:47–88`
- Quiz generation/grading: `backend/src/main/java/com/careercompass/service/QuizService.java:54–180`
- Job/candidate matching: `backend/src/main/java/com/careercompass/service/JobMatchService.java:53–173`
- FastAPI routes: `ai-service/src/careercompass/api/app.py:254–950`
- Pydantic contracts: `ai-service/src/careercompass/api/schemas.py:79–292`
- Python error contract: `ai-service/src/careercompass/api/errors.py:17–42,188–236`
- Python module readiness: `ai-service/docs/PROJECT_STATUS.md:14–36,74–83`

## Appendix B — Principal requirement evidence

- Canonical Job Seeker requirements: `/home/almadhoun/Desktop/CareerCompass/requirements/Combined_requirements.txt:60–64,93–95,119–124,158–160`
- Performance/reliability/security/AI NFRs: `/home/almadhoun/Desktop/CareerCompass/requirements/Non_Functional_Requirements.txt:45–118,130–189,253–340`
- AI pipeline and six modules: `/home/almadhoun/Desktop/CareerCompass/planning/Section_5_3_AI_Pipeline.md:8–126`
- UI behavior: `/home/almadhoun/Desktop/CareerCompass/planning/Interface_Design.md:114–216`
- Detailed internal FR-AI-01…14: `/home/almadhoun/Desktop/CareerCompass/CoursesSuggestionsystem_v6.docx`, §4.3.6
- Existing Java-side service contract: `docs/contracts/AI_SERVICE_CONTRACT.docx`
