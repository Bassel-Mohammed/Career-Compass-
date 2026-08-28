# Project Status Report

**Date:** 2026-08-27
**Branch audited:** `integration/full-stack` @ `8ac973e` (plus uncommitted working-tree changes)
**Audit method:** static review + full automated test runs + live black-box testing against the running Docker stack

---

## Summary

CareerCompass is a three-service monorepo: a **Java 17 / Spring Boot 3.3.4** API (`backend/`), a **Python 3.10+ / FastAPI** AI service (`ai-service/`), and a **React 19 / Vite 8 / TypeScript** SPA (`frontend/`). Spring owns auth, RBAC, and persistence (H2 dev / MySQL prod, Flyway-managed); FastAPI owns transcript & syllabus parsing, the skill taxonomy, gap analysis, recommendations, and quiz generation (PostgreSQL, own migration runner). The two speak a versioned internal contract (`docs/contracts/careercompass-ai-internal-v1.yaml`) over HTTP with a shared bearer token.

**The engineering quality here is well above average.** All 452 automated tests pass. Authentication, role isolation, IDOR protection, input validation, empty-state handling, optimistic concurrency, and token revocation were each verified live and all behave correctly. CI covers seven jobs including real MySQL and PostgreSQL migration rehearsals. Architectural decisions are documented in 8 ADRs, and the code comments explain *why* rather than *what* to an unusually high standard.

The blockers are **operational, not architectural**. Four issues stand between this and production:

1. **A forged admin token is accepted when `JWT_SECRET` is unset** — verified empirically, not theoretical.
2. **The course-map publish workflow is broken for every course after the first** — a global vs. per-course version namespace mismatch, confirmed against live data.
3. **Every HTTP 500 is silently swallowed** — zero log output, verified.
4. **The frontend does not currently build** — uncommitted test scaffolding breaks `tsc`.

Items 1, 3, and 4 are small, contained fixes. Item 2 needs a migration and a decision about the version namespace.

---

## Test Results

### Automated suites

| Suite | Command | Result |
|---|---|---|
| Backend (JUnit) | `JAVA_HOME=.../java-17-openjdk-amd64 mvn -B test` | ✅ **222 run, 0 failures, 0 errors, 6 skipped** — BUILD SUCCESS |
| AI service (pytest) | `CC_EMBEDDING_BACKEND=lexical CC_API_WARMUP=0 uv run --extra dev pytest -q` | ✅ **230 passed**, 1 warning |
| Frontend (vitest) | `npx vitest run` | ✅ **14 passed, 3 files** |
| Frontend build | `npm run build` | ❌ **FAILS** (`tsc -b`, exit 1) |
| Frontend lint | `npm run lint` (oxlint) | ⚠️ passes with **6 warnings** |
| Frontend deps | `npm ci` | ✅ 166 packages, **0 vulnerabilities** |
| Python deps | `pip-audit` | ✅ **No known vulnerabilities** |

The 6 skipped backend tests are `HttpDataAnalysisClientLiveContractTest` — they require a live AI service and self-skip otherwise. That is correct behaviour, not a gap.

**Backend requires JDK 17 explicitly.** This machine defaults to JDK 25, on which Lombok 1.18.34 fails. Documented in `TASKS.md`, matches `.github/workflows/ci.yml`.

### The frontend build failure

`npm run build` fails on 20 TypeScript errors. **This is entirely uncommitted work-in-progress** — verified by building `HEAD` in a clean detached worktree, which succeeded (658 modules, 240ms, chunks: `index` 384 kB / 111 kB gzip, `charts` 355 kB / 103 kB gzip).

Failing files, all untracked or modified:

- `frontend/src/api/errors.test.ts` — 10 errors: unused import (line 2); `{}` passed where `FieldError[]` expected (lines 8, 13, 29–36, 42, 51); wrong arity and argument type (lines 18, 19)
- `frontend/src/pages/LoginPage.test.tsx:74` — `{}` where `FieldError[]` expected
- `frontend/src/test/utils.tsx:1-2` — type-only imports required under `verbatimModuleSyntax`
- `frontend/src/pages/expert/ExpertProfilePage.tsx:1` — unused `useState` import
- `frontend/vite.config.ts:7` — `test` key not valid in `UserConfigExport`; needs `/// <reference types="vitest/config" />` or import from `vitest/config`

**Vitest passes because it transpiles via esbuild and never typechecks** — the suite is green while the build is red. CI runs `npm run build`, so committing this as-is turns CI red.

### Live functional testing

I exercised the running Docker stack (all five containers healthy) end-to-end. Everything below was executed against real HTTP, not mocked.

**Working correctly:**

| Feature | Evidence |
|---|---|
| Auth (5 actors) | Login returns HS384 JWT + role + 1800s expiry for all roles |
| Unauthenticated / bad token | 401 with structured `ApiErrorResponse` (not Spring's default 403) |
| Cross-role isolation | Full 4×3 matrix: 200 on-diagonal, **403 on every off-diagonal cell** |
| IDOR | Employer B `PUT`/`DELETE` on employer A's job → **403 both** |
| Input validation | Short password → 400 + per-field errors; duplicate email → 409; bad credentials → 401 with non-enumerating message |
| Empty states | New student gets `PREREQUISITE_NOT_MET` with actionable text on 4 endpoints, `[]` on 2 |
| Transcript parse | Real PDF → 71 structured courses in 0.36s; non-PDF → 400 "Only PDF files are accepted" |
| Skill dashboard | 27% readiness, 105 skills, 33 counted / 10 skipped / 27 synthetic, 184-posting market sample |
| Career-path skills | 105 skills banded critical/important/useful from real job-posting data |
| Course recommendations | Real Coursera links with market-grounded explanations |
| Mentor matching | Match scores + human-readable reasons |
| Quiz generation | **Works** (LLM via host Ollama) — answer key correctly hidden pre-submit, revealed post-submit; score updates dashboard |
| Learning-outcome pipeline | Upload → extract (**~8s**, 47 drafts) → review → publish gate |
| Optimistic concurrency | Stale `expectedDraftRevision` → **409**, correctly rejected |
| Business-rule gates | Cannot accept an unresolved term; cannot publish with 46 pending; cannot publish duplicate canonical skills |
| Appointments | Booking → 201; past date → 400 |
| Logout | 204, then **reused token → 401** (revocation works) |
| Upload cap | 12 MB PDF → **413** `FILE_TOO_LARGE` |
| Concurrent reads | 20 parallel dashboard reads → **20 × 200** |
| AI service auth | No token → 401 RFC 9457 problem doc; constant-time compare |
| Job matching | 501 `AI_CAPABILITY_NOT_IN_SCOPE` — **descoped by design**, documented in README |

**Not verified:** browser-level UI behaviour, accessibility, and visual rendering. I tested the API surface and read the React source; I did not drive the SPA in a browser. Marked **Unverified**.

---

## Missing / Incomplete Functionality

### 🔴 Course-map publishing is broken for every course after the first

**Confirmed against live data — this is the most serious functional defect.**

The backend numbers course-map versions **per course**:

```java
// backend/src/main/java/com/careercompass/service/LearningOutcomeReviewService.java:549-550
long mapVersion = mapVersionRepository.findLatestMapVersion(
        outcome.getInstitutionCode(), outcome.getCatalogVersion(), outcome.getCourseCode()) + 1;
```

…and sends it as a bare string (`"1"`, `"2"`, …) at `LearningOutcomeReviewService.java:606`.

The AI service stores it under a **global** primary key:

```sql
-- ai-service/src/careercompass/db/migrations/006_course_map_publications.sql:10
course_map_version   VARCHAR(120) PRIMARY KEY,
```

The lookup at `ai-service/src/careercompass/db/course_maps.py:78-85` finds any row with that version string, sees a different course identity, and raises `CourseMapVersionConflict`.

**Consequence:** the first course ever published claims `"1"` globally. Every subsequent course's first publish collides and fails permanently.

Live proof — publishing course `AUDIT101` returned:

```
502 AI_SERVICE_REQUEST_REJECTED
"Version '1' was already published with different content. Create a new version for the revised map."
```

…because course `0413203` already held version `"1"`:

```
 course_map_version | institution_code | catalog_version | course_code | source_outcome_id
--------------------+------------------+-----------------+-------------+-------------------
 4                  | UNI:1            | 2026            | ZZ999       | 5
 1                  | UNI:1            | 2025-2026       | 0413203     | 10
```

The table already carries the correct scoping as a secondary constraint — `uq_course_map_identity_version UNIQUE (institution_code, catalog_version, course_code, course_map_version)`. The fix is to make **that** the primary key (or have Java send a globally-qualified version string). Requires a migration; `course_map_heads` has an FK onto the current PK.

Note the error surfaces as **502** to the client, implying an AI-service fault, when it is really a 409-class contract conflict.

### 🔴 Concurrent writes to the same resource return 500

10 parallel `POST /api/job-seekers/me/transcript/confirm` for one student: **1 × 200, 9 × 500**. Reproduced at 5 parallel: 1 × 200, 4 × 500.

The write path has no optimistic-lock or constraint-violation handling, so the underlying exception falls through to the catch-all handler. This should be a **409** with a retry-safe message. Reads are unaffected (20/20 × 200).

Note the learning-outcome review path *does* implement optimistic concurrency correctly — the pattern exists in the codebase and simply is not applied here.

### 🟡 Extractor precision forces heavy manual dedup

On one syllabus, 27 accepted draft terms collapsed onto only **12 distinct canonical skills**:

- `custom:database-design` ×9 — "Normalization", "Modeling", "Relationship Model", "Relational Database Design", "Entity Relationship Modeling", …
- `esco:598de5b0…` (SQL) ×3, `esco:de9f85ba…` ×3, `esco:ab1e97ed…` ×3, `esco:43ae58b9…` ×2

Junk terms also appear as drafts ("tables", "EERD"), and at least one mis-mapping ("data management" → *SAS Data management*).

Publishing is blocked until duplicates are resolved, so a content manager must hand-remove ~15 rows per syllabus. The UI *does* flag duplicates (`frontend/src/pages/content/LearningOutcomeReviewPage.tsx:289,354,452`), so this is a **quality/throughput** problem, not a correctness one — but it makes the feature laborious at scale. There is no bulk "remove all duplicates" action.

### 🟡 Smaller gaps

- **Quiz `questionCount` not honoured** — requested 3, received 2. The LLM returns fewer than asked and nothing reconciles it.
- **Descoped by design (documented, not defects):** AI job matching returns 501 for both `/api/job-seekers/me/job-matches` and `/api/employers/me/jobs/{id}/candidates`.
- **Open items in `TASKS.md`:** T7 (make pytest suites runnable), T8 (code-split charts — appears partly done, `charts` is already a separate chunk), T9 (mentor match-score scale).

---

## Security & Config Gaps

### 🔴 CRITICAL — Production can start with a publicly-known JWT signing key

`backend/src/main/resources/application.yml:36` supplies a fallback:

```yaml
secret: ${JWT_SECRET:CHANGE_ME_LOCAL_DEV_ONLY_NOT_FOR_PRODUCTION_1234567890}
```

`application-prod.yml` does **not** override `careercompass.jwt`, and `JwtProperties.java:18` has **no** `@NotBlank`, `@Validated`, or startup assertion. A production deploy that forgets `JWT_SECRET` starts silently on a secret published in this repository.

**Verified empirically.** I minted an admin JWT offline using only the value published in `compose.yaml` — no login, no credentials — and the running backend accepted it:

```
GET /api/admin/universities  ->  HTTP 200
```

Anyone reading the repo can forge a token for any role and any user id.

This is inconsistent with how the same file treats the AI service, which is done correctly: `application-prod.yml:23,29` deliberately omit defaults for `AI_SERVICE_BASE_URL` and `AI_SERVICE_TOKEN` so startup *fails* when they are missing. `ai-service/src/careercompass/api/auth.py:20-22` documents exactly this reasoning. **Apply the same rule to `JWT_SECRET`.**

**Fix:** remove the default, add `@NotBlank` + `@Validated` to `JwtProperties`, and reject secrets shorter than 32 bytes at startup.

### 🔴 HIGH — Unexpected errors are never logged

```java
// backend/src/main/java/com/careercompass/exception/GlobalExceptionHandler.java:190-196
@ExceptionHandler(Exception.class)
public ResponseEntity<ApiErrorResponse> handleUnexpected(Exception ex, HttpServletRequest request) {
    // ... real logging of `ex` happens via the logging framework, not shown here.
    return build(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", ...);
}
```

The comment asserts logging happens elsewhere. **It does not** — the file contains **zero** `log.` calls and no `@Slf4j`. The exception object is discarded.

**Verified:** the 9 concurrent-write 500s above produced **no output whatsoever** in `docker logs` across 855,807 log lines. In production, every 500 would be invisible — no stack trace, no message, no correlation id. This single missing line is the difference between a debuggable incident and a blind one.

**Fix:** add `@Slf4j` and `log.error("Unhandled exception on {}", request.getRequestURI(), ex);`.

### 🟠 MEDIUM

- **CORS hardcoded to localhost** — `SecurityConfig.java:168-169` pins origins to `http://localhost:3000` and `:5173` with a `TODO`. No env-var override exists, so any real deployment needs a code change. With `setAllowCredentials(true)`, getting this wrong is consequential.
- **No rate limiting or account lockout** — all six login endpoints accept unlimited attempts. No `bucket4j`/`resilience4j`, no failed-attempt tracking anywhere in `backend/src/main/java/`. Passwords are BCrypt-hashed (good), but online brute force is unthrottled.
- **JWT in `localStorage`** — `frontend/src/auth/session.ts:31,56`. XSS-exfiltratable. A common, defensible tradeoff, but it should be a recorded decision.
- **`/h2-console/**` is `permitAll`** in the shared security chain (`SecurityConfig.java:90`). The console itself is only enabled in `dev`, so this is not currently exploitable — but the rule should be profile-scoped as defence in depth. `frameOptions.sameOrigin()` (line 109) is likewise global for the console's benefit.
- **User enumeration on registration** — duplicate email returns 409 echoing the address. Login correctly avoids this ("Invalid email or password"); registration does not. Usually an accepted UX tradeoff — flagging for an explicit decision.
- **Spring Boot 3.3.4** (Sept 2024) is ~2 years old and past OSS support. **Unverified:** no CVE scan was run against the Java dependency tree — `npm audit` and `pip-audit` both came back clean, but there is no equivalent result for Maven. Add OWASP Dependency-Check or Dependabot.

### 🟡 Config & deployment fragility

- **Hardcoded Docker bridge gateway** — `compose.yaml` sets `AI_SERVICE_BASE_URL: http://172.18.0.1:8000`. This IP is assigned by Docker and varies by host and network creation order. Brittle; a consequence of `ai-service` using `network_mode: host`.
- **Undocumented external dependency on Ollama** — `compose.yaml` sets `CC_MATCH_LLM: "1"` and `CC_OLLAMA_URL: http://localhost:11434`, requiring a host-installed Ollama with `qwen3:8b`. This **contradicts the README**, which states "The default stack deliberately disables optional model downloads and LLM calls" and "quiz generation remains unavailable". Quiz generation in fact **works** on this machine because Ollama is running. A fresh clone on a machine without Ollama will behave differently from this one, and nothing documents the prerequisite.
- **`VITE_API_BASE_URL` fails open** — `frontend/src/api/client.ts:3` falls back to `http://localhost:8080`. A production build missing the variable silently ships a bundle pointing at the user's own machine, failing at runtime rather than build time.
- **`frontend/.env.development` is gitignored** (`.gitignore` `.env.*`) so a fresh clone lacks it. Harmless today only because of the fallback above.
- **11 uploaded PDFs are tracked in git** under `backend/uploads/learning-outcomes/` despite the ignore rule added later — they predate it. Runtime upload data does not belong in version control.

**Good news on secrets:** no `.env` file, `ACCOUNTS.txt`, or `backups/` content is tracked. Only `ai-service/.env.example` is committed, and it contains placeholders. `ACCOUNTS.txt` holds plaintext demo passwords but is correctly gitignored. `ai-service/.env` contains no API keys — the local Ollama path needs none.

---

## Documentation Gaps

- **README contradicts `compose.yaml`** on LLM availability (see above). The most misleading doc issue in the repo — it tells a new developer a feature is unavailable when it is running.
- **OpenAPI is wrong for multipart uploads.** `POST /api/content-managers/me/learning-outcomes` documents only `file` as required, but `ContentManagerController.java:72-78` also requires `courseCode`, `catalogVersion`, and `courseName` as `@RequestParam`. A client written from the spec gets a 400. springdoc does not infer these; they need `@Parameter`/`@RequestPart` annotations. Confirmed live.
- **No `docker-compose.prod.yml`** — the only compose file is the dev stack. `deployplan.md` lists creating one as an open step.
- **Ollama / `qwen3:8b` setup is documented nowhere** — not in the root README, `ai-service/README.md`, or `compose.yaml` comments.
- **No runbook** — nothing documents deploy, rollback, backup/restore, or incident response. `docs/database-operations.md` covers DB procedures only.
- **`ai-service/README.md` test command is stale** — it recommends `../.venv/bin/pip install pytest` and `PYTHONPATH=src python -m pytest`; CI uses `uv run --extra dev pytest -q`. `TASKS.md` T7 tracks this.
- **No env-var reference.** `CC_*` variables are spread across `.env.example`, `compose.yaml`, and code defaults with no single table. `CC_INCLUDE_MOCK_COURSES`, `CC_API_WARMUP`, and `CC_DB_LOAD_REVIEWS` are especially easy to miss.
- **Strengths worth preserving:** 8 ADRs in `docs/adr/`, a versioned OpenAPI contract validated in CI, `backend/db/README.md`'s Flyway baseline procedure, and consistently excellent in-code rationale comments.

---

## Deployment Readiness Checklist

### Build process — ⚠️ Partially Ready
- ❌ Frontend `npm run build` fails on 20 `tsc` errors in uncommitted test scaffolding
- ✅ Frontend builds cleanly at `HEAD` (verified in isolated worktree)
- ✅ Backend `mvn package` succeeds (JDK 17)
- ✅ AI service wheel builds; CI installs and migrates from the wheel
- ⚠️ 6 lint warnings
- ❌ `frontend/Dockerfile` runs the **Vite dev server** (`npm run dev`) — explicitly a dev image, unsuitable for production
- ✅ `backend/Dockerfile` is production-shaped: multi-stage, JRE-alpine, non-root user

### Environment & secrets management — ❌ Not Ready
- ❌ `JWT_SECRET` defaults to a repo-published value; forged admin token **verified accepted**
- ❌ No startup validation on secret presence or length
- ✅ `AI_SERVICE_BASE_URL` / `AI_SERVICE_TOKEN` correctly have no prod defaults
- ✅ AI service refuses to default its token; constant-time comparison
- ✅ No secrets tracked in git
- ⚠️ CORS origins hardcoded to localhost
- ⚠️ `VITE_API_BASE_URL` silently falls back to localhost
- ⚠️ No consolidated env-var documentation

### Database migrations / seed data — ✅ Ready
- ✅ Flyway owns the backend schema; `baseline-on-migrate: false`, `validate-on-migrate: true`; Hibernate in `validate` mode
- ✅ V1→V5 chain (V2/V3 are Java migrations under `src/main/java/db/migration/`)
- ✅ AI service has a checksum-validated, advisory-locked migration runner (`cc-db-migrate`), 6 migrations
- ✅ CI rehearses **fresh and legacy-upgrade** paths on real MySQL 8.4 and PostgreSQL 17
- ✅ `DevDataSeeder` is `@Profile("dev & !test")` — cannot leak into prod
- ✅ Documented baseline procedure for pre-existing databases
- ⚠️ AI service `006` PK choice is the root cause of the publish defect (see above)

### Monitoring, logging, error tracking — ❌ Not Ready
- ❌ **500s are never logged** — verified zero output for 9 real 500s
- ❌ No Spring Actuator — no `/health`, `/metrics`, or `/info`
- ❌ No error tracking (no Sentry/OTel/Prometheus in any of the three manifests)
- ❌ No structured/JSON logging; no `logback-spring.xml`; console only
- ❌ No request correlation ids
- ⚠️ Backend compose healthcheck probes `/v3/api-docs` — a docs endpoint standing in for a health check, and public
- ✅ AI service has real `/health/live` and `/health/ready` probes
- ✅ AI service logs auth state at startup

### CI/CD pipeline — ⚠️ Partially Ready
- ✅ 7 jobs: migration layout, frontend build+lint, AI tests, AI PostgreSQL migrations, OpenAPI contract validation, backend compile, backend tests, backend MySQL migrations
- ✅ Runs on every push to `main` and every PR, with `cancel-in-progress` concurrency
- ✅ Uploads surefire reports on failure
- ❌ **No CD** — no build/push/deploy stage anywhere
- ❌ No frontend test job — `npm run test` is never invoked in CI, so the 14 vitest tests never run there
- ❌ No dependency/CVE scanning job
- ❌ No coverage measurement or gate

### Rollback / recovery — ❌ Not Ready
- ❌ No documented rollback procedure
- ❌ No Flyway `undo` migrations (Teams-only feature) and no forward-fix policy written down
- ❌ No image tagging or versioning strategy; `0.1.0-SNAPSHOT`
- ❌ No automated backups; `backups/` holds one manual dump from 2026-08-24
- ✅ `docs/database-operations.md` and `docs/database-migration-verification.md` exist as a partial foundation

### Performance / load — ⚠️ Partially Ready
- ✅ Per-operation AI timeout budgets, not one blanket value (`application.yml:51-59`)
- ✅ Hikari pool capped at 10 (`application-prod.yml:8`)
- ✅ 10 MB upload cap enforced → 413
- ✅ 20 concurrent reads all 200
- ✅ Transcript parse 0.36s; extraction ~8s; dashboard 0.13s
- ❌ Concurrent writes to one resource → 500
- ⚠️ ~740 kB raw / ~214 kB gzipped JS across two chunks
- ❌ No load testing performed — **Unverified** under sustained or realistic concurrency
- ⚠️ Quiz generation depends on local LLM inference latency

### Security review — ❌ Not Ready
- ❌ Forgeable admin tokens when `JWT_SECRET` unset (**verified**)
- ❌ No login rate limiting or lockout
- ⚠️ CORS hardcoded; `/h2-console/**` permitted chain-wide; JWT in `localStorage`
- ⚠️ Spring Boot 3.3.4 outdated; **no Java CVE scan run (Unverified)**
- ✅ BCrypt hashing; stateless JWT; correct 401/403 split
- ✅ Role isolation verified across the full matrix; IDOR blocked
- ✅ Bean-validation on inputs; file-type and size enforcement
- ✅ Token revocation on logout verified
- ✅ Service-to-service auth with constant-time compare
- ✅ Quiz answer keys not exposed pre-submission
- ✅ `npm audit` and `pip-audit` both clean

### Scalability — ⚠️ Partially Ready
- ✅ Stateless JWT sessions — horizontally scalable in principle
- ❌ **Local-disk file storage** (`FileStorageService`) breaks multi-instance deployment; acknowledged in `application.yml:63-66` and in `deployplan.md`
- ❌ `network_mode: host` + hardcoded `172.18.0.1` prevents clean orchestration
- ❌ Dev stack uses file-backed H2, not MySQL
- ⚠️ In-process AI matcher index; ~5 min warm-up start period
- ⚠️ Revoked-token table needs a purge strategy for unbounded growth

---

## Overall Deployment Readiness Score

# ⚠️ 55% — Partially Ready (not deployable today)

**Reasoning.**

What exists is genuinely solid. The **application logic is production-grade**: 452 passing tests, verified role isolation across a full 4×3 matrix, IDOR protection, thorough input validation, thoughtful empty states, optimistic concurrency in the review workflow, working token revocation, and a real AI pipeline delivering market-grounded output end-to-end. Migration discipline is better than most production systems — Flyway with validation on, Hibernate in `validate` mode, checksum-locked Python migrations, and CI rehearsing both fresh and upgrade paths against real MySQL and PostgreSQL. The security *architecture* is correct; ADRs explain the decisions.

What is missing is the **operational layer around it**, and two defects that would surface immediately in production:

- A **forged admin token was accepted** using only a value published in this repository. Not theoretical — demonstrated.
- **Course-map publishing fails for every course after the first**, confirmed against live data. A core content-manager workflow is unusable beyond one course.
- **Every 500 vanishes silently.** Verified across 855k log lines. Production incidents would be undiagnosable.
- **The working tree does not build**, so CI is red until the test scaffolding is fixed or reverted.

Add to that: no CD, no rollback plan, no monitoring, no metrics, no error tracking, a dev-server frontend image, and local-disk storage that prevents running more than one instance.

The gap is **breadth of operational readiness, not depth of engineering quality**. Nothing here requires re-architecture. The critical fixes are hours of work: one validation annotation, one log line, one migration, one `tsc` cleanup. The infrastructure work — CD, monitoring, object storage, a production compose file — is well-scoped and already correctly identified in `deployplan.md`.

**Realistic path:** ~1 day to clear the four blockers; ~1–2 weeks to reach genuine production readiness.

---

## Recommended Next Steps

### P0 — Blockers (do before any deployment)

1. **Fail startup when `JWT_SECRET` is absent or weak.** Remove the default from `application.yml:36`; add `@NotBlank` + `@Validated` to `JwtProperties.java:18`; reject secrets under 32 bytes. Mirror the pattern already used correctly for `AI_SERVICE_TOKEN` in `application-prod.yml:29`. *Then rotate the compose default, which is now public.*
2. **Log unhandled exceptions.** Add `@Slf4j` to `GlobalExceptionHandler` and `log.error("Unhandled exception on {}", request.getRequestURI(), ex);` at line 193. One line; removes a total operational blind spot.
3. **Fix the course-map version namespace.** Promote `uq_course_map_identity_version` to the primary key of `course_map_publications` (new migration `007`, updating the `course_map_heads` FK), *or* have `LearningOutcomeReviewService.java:606` send a globally-qualified version. Add a regression test publishing two different courses at version 1. Also map this conflict to **409**, not 502.
4. **Make the frontend build.** Fix the 20 `tsc` errors (or revert the scaffolding): type the `FieldError[]` fixtures, drop unused imports, use type-only imports in `test/utils.tsx`, and import `defineConfig` from `vitest/config` in `vite.config.ts`.

### P1 — Before real users

5. **Handle concurrent writes.** Catch optimistic-lock/constraint violations on the transcript-confirm path and return **409**; reuse the pattern already working in `LearningOutcomeReviewService`.
6. **Add rate limiting** to all six login endpoints (bucket4j or a filter), plus failed-attempt backoff.
7. **Make CORS configurable** — replace the hardcoded list at `SecurityConfig.java:168-169` with an env-driven property.
8. **Add Spring Actuator** with `/health` and `/metrics`; repoint the compose healthcheck away from `/v3/api-docs`.
9. **Add a production frontend image** — multi-stage build serving static `dist/` via nginx — and make `VITE_API_BASE_URL` required at build time instead of falling back to localhost.
10. **Reconcile README with `compose.yaml`** on LLM/quiz availability, and document the Ollama + `qwen3:8b` prerequisite.

### P2 — Production hardening

11. **Move file storage to S3/R2** — `FileStorageService` currently blocks horizontal scaling (already scoped in `deployplan.md` step 2).
12. **Add CD** — build, tag, push images; add a deploy stage; write the rollback procedure.
13. **Add error tracking** (Sentry or OTel) and structured JSON logging with request correlation ids.
14. **Add dependency scanning** to CI (OWASP Dependency-Check / Dependabot) and plan the Spring Boot 3.3.4 upgrade.
15. **Run `npm run test` in CI** — the frontend job currently builds and lints but never runs the 14 existing tests.
16. **Fix the OpenAPI multipart schema** for the learning-outcome upload so generated clients work.
17. **Replace the hardcoded `172.18.0.1`** — drop `network_mode: host` and use Docker service DNS.
18. **Automate database backups** with a documented restore rehearsal.

### P3 — Quality & maintainability

19. **Add coverage measurement** (JaCoCo / pytest-cov / vitest --coverage) — none exists today.
20. **Expand frontend tests** — 3 test files cover 68 source files; prioritise `ProtectedRoute`, `AuthProvider`, and `session.ts`.
21. **Improve extractor precision** or add bulk-dedup to the review UI — 27 terms → 12 canonical skills is a real throughput tax.
22. **Untrack the 11 committed upload PDFs** under `backend/uploads/learning-outcomes/`.
23. **Add a purge policy** for the revoked-token table.
24. **Write a runbook** — deploy, rollback, backup/restore, incident response.
25. **Close out `TASKS.md`** T7–T9 and refresh the stale test command in `ai-service/README.md`.

---

# UI Audit — Missing Implementation

**Added:** 2026-08-27
**Method:** Playwright (Chromium) driving the running stack at `http://localhost:5173`. Every route was visited as every one of the five actors; forms were filled, buttons clicked, and flows run to completion. Console errors, failed requests, and non-2xx backend responses were captured per page. 28 full-page screenshots taken at 1400px and 375px.

**Coverage:** all 21 routed pages × 5 roles, plus `/login`, `/signup`, and a 404. Interactive flows executed: login (5 roles), signup form, quiz generation → answering → submission, mentor session accept, admin create-forms (content manager / mentor / career path), employer job create, and appointment booking.

**Overall:** the UI is more polished and more complete than the audit above implied. Copy is written for humans, empty states are genuinely helpful, error states explain what to do next, destructive actions are confirmed, and the 501 descope is communicated clearly rather than shown as a crash. What follows are the gaps found *within* that quality.

---

## A. Features with a working backend but no UI

These endpoints exist, are tested, and are reachable — but nothing in the app calls them. The work is done server-side and stranded.

### A1. 🔴 Students can never see posted jobs — the employer pipeline dead-ends

`JobService.listActiveJobs(Pageable)` ([JobService.java:93-94](backend/src/main/java/com/careercompass/service/JobService.java#L93-L94)) is implemented **and paginated** — but **no controller exposes it**. Enumerating all 61 documented paths confirms the only job endpoints are `/api/employers/me/jobs` (an employer's own postings) and `/api/job-seekers/me/job-matches` (which returns 501).

Consequence: an employer creates a posting, it saves successfully, and **no student can ever see it by any route**. The student `/jobs` page shows only the descope notice. Because AI matching is descoped *and* there is no plain listing fallback, the entire employer→student flow — the thing the employer role exists for — produces nothing.

This is the single largest functional hole in the product. A read-only `GET /api/job-seekers/me/jobs` wired to the existing paginated service method would close it without touching the AI service.

### A2. 🟠 Mentors cannot see their mentee's skill profile

`getJobSeekerDashboard()` and `getJobSeekerRecommendations()` exist in `frontend/src/api/expert.ts` and are backed by two live endpoints ([ExpertController.java:79,85](backend/src/main/java/com/careercompass/controller/ExpertController.java#L79-L85)). **Neither is called from any page** — grep across all `.tsx` returns nothing.

So a mentor accepts a consultation and arrives with no idea what the student is weak in, despite the platform having computed exactly that. The obvious home is a link from each session card on `/expert`.

### A3. 🟠 Content managers cannot set their own study field

`frontend/src/pages/content/StudyFieldPage.tsx` is fully written but **never imported and never routed** — `App.tsx` registers only `/content` and `/content/learning-outcomes/:outcomeId/review`. The `CONTENT_MANAGER` nav in [nav.ts](frontend/src/auth/nav.ts) has exactly one entry.

The backing API is complete on both sides (`PUT /api/content-managers/me/study-field`, `contentManager.selectStudyField()`). A content manager's study field is currently settable only by an administrator. Add the route and one nav item.

### A4. 🟡 Dead component

`frontend/src/pages/PlaceholderHome.tsx` is never imported. Delete it.

---

## B. Features missing entirely (no backend, no UI)

### B1. 🔴 No password reset — an account whose password is forgotten is unrecoverable

`grep -riE 'forgot.?password|reset.?password'` across `backend/src/main/java` and `frontend/src` returns **nothing**. There is no link on the login page, no endpoint, no token table.

For self-registered students and employers this is terminal: the only recovery path is an administrator editing the database directly. Mentors and content managers at least have an admin who can recreate them.

### B2. 🔴 No change-password anywhere

No `changePassword`, `currentPassword`, or `oldPassword` symbol exists in either service. A signed-in user of **any** role cannot rotate their own credentials. Combined with B1, a password is set once at registration and is then immutable for the life of the account.

Note the student `/profile` page *does* implement account deletion properly, with a confirm dialog ([ProfilePage.tsx:143-167](frontend/src/pages/student/ProfilePage.tsx#L143-L167)) — so the danger-zone pattern already exists to hang this off.

### B3. 🟠 No email capability at all

No `JavaMailSender`, no `spring-boot-starter-mail`, no SMTP configuration. Therefore: no email verification, no password-reset delivery (blocking B1), and **no notification when a mentor accepts or rejects a session**. A student must return to the site and re-check manually. There is no in-app notification mechanism either — no polling badge, no websocket, no SSE.

### B4. 🟡 Reference data is create-only

`/admin/reference` offers **Add** for universities and study fields, but no Edit and no Delete — and `AdminController` has no such endpoints either, so the UI is faithful to the API. A typo in a university name is permanent. Career paths, by contrast, have full CRUD (Edit + Delete present and working).

---

## C. Broken behaviour found by driving the UI

### C1. 🔴 Mentor availability is collected and then ignored

`/expert/availability` is a complete, polished page for setting weekly recurring slots, saved through `PUT /api/experts/me/availability`.

**Nothing ever reads it.** `grep -n 'vailability' ConsultationService.java` returns nothing — the booking path never consults `ExpertAvailability`. The student picks any moment via a bare `datetime-local` input ([MentorsPage.tsx:134](frontend/src/pages/student/MentorsPage.tsx#L134)).

Verified: I booked a mentor for `2026-09-20T14:00` while that mentor had **no availability set at all** → `201 Created`. An entire feature loop is decorative.

### C2. 🔴 No double-booking prevention

Three identical `POST /api/job-seekers/me/appointments` for the same mentor at the same instant (`2026-10-01T09:00:00`) all returned **201**, producing three appointments in the same slot. No uniqueness constraint, no overlap check, and no guard against a mentor being booked by several students simultaneously.

### C3. 🟠 Past Sessions lists future, unaccepted appointments

On `/expert`, a pending appointment dated **Sep 20 2026** appeared simultaneously under *Upcoming Sessions* and *Past Sessions*.

Backend cause, not a display bug:
- [ExpertService.java:103-105](backend/src/main/java/com/careercompass/service/ExpertService.java#L103-L105) — `getScheduledSessions` correctly filters `appointmentDate > now`
- [ExpertService.java:112-113](backend/src/main/java/com/careercompass/service/ExpertService.java#L112-L113) — `getConsultationHistory` applies **no date and no status filter**, returning every appointment

Both endpoints return the identical single-element array. History should be past-dated, or Completed/Rejected.

### C4. 🟠 Session status goes stale after accepting

Clicking **Accept** correctly moved the card to `Status: Accepted` under Upcoming — while the same appointment under Past Sessions still read `Status: Requested`. The history query is not invalidated after the mutation, so one screen shows one appointment in two contradictory states.

### C5. 🟠 Mentor match scores do not discriminate

All five mentors scored **40.75 / 38.25** — two distinct values across five people — while `gapsAddressed` ranged from **43 to 77**. Four of five are byte-identical at 40.75, so the UI shows "Match Score: 41%" four times. A ranking that assigns nearly everyone the same number cannot rank. This is `TASKS.md` **T9**, confirmed live.

### C6. 🟠 Invalid HTML nesting on the dashboard

React logs DOM-nesting validation errors on `/dashboard`: `<summary>`, `<ul>`, and `<details>` each rendered as descendants of `<p>`. React's own warning says this "will cause a hydration error". The page renders today, but this is invalid HTML and a genuine SSR/hydration hazard.

### C7. 🟠 Horizontal overflow on mobile

At a 375 px viewport:

| Route | scrollWidth | clientWidth | |
|---|---|---|---|
| `/login` | 375 | 375 | ✅ |
| `/dashboard` | **443** | 375 | ❌ overflows |
| `/courses` | **406** | 375 | ❌ overflows |

The marketing/login surface is responsive; the authenticated app is not. Likely the chart and wide card grids need `overflow-x: auto` containers.

### C8. 🟡 Saved course recommendations lose their reasoning

`/courses` renders its own apology: *"Which skill each one targets is not stored with them — regenerate to see that and the reasoning again."*

Root cause: `CourseRecommendation` persists only `courseName`, `sourceLink`, and `recommendedAt` ([CourseRecommendation.java:23-37](backend/src/main/java/com/careercompass/entity/CourseRecommendation.java#L23-L37)). The generate call returns `targetedSkillName` and `explanation` — genuinely good, market-grounded copy — and both are **discarded on save**. Two columns would fix it.

### C9. 🟡 Production quiz timeout is set below observed generation time

Quiz generation completed somewhere between **25 s and 70 s** in the UI (still rendering "Writing your quiz…" at 25 s; complete by 70 s). `application.yml:56` allows 60 s, but [application-prod.yml:35](backend/src/main/resources/application-prod.yml#L35) pins `quiz-seconds: 15`.

On this hardware a production deployment would time out on **every** quiz. Whether a hosted LLM is faster is **Unverified** — but 15 s is not justified by any measurement taken here.

---

## D. What the UI does well

Worth recording so it is not lost in a defect list:

- **Empty and prerequisite states are excellent** — "Upload and confirm your transcript before viewing your skill dashboard" names the action, not the error.
- **The 501 descope is handled gracefully** on both `/jobs` and `/employer/jobs/:id/candidates`, with honest copy explaining what still works.
- **Synthetic data is labelled on screen** — the dashboard states that 27 of 33 courses use synthetic syllabi and that the market figures are real. This is the honesty condition `TASKS.md` set for using the mock corpus, and it is met.
- **The review page is the strongest screen in the app** — priority triage (`Blocked 12 / Judgment 32 / Quick 0`), inline duplicate warnings, per-row evidence, and a publish button correctly disabled until the draft is clean.
- **Destructive actions are confirmed** — account deletion uses a typed confirm dialog.
- **Accessibility basics pass on `/login`** — 0 unlabelled inputs, 0 images without `alt`, 0 buttons without accessible text, `lang="en"`, exactly one `<h1>`.
- **Forms disable their submit until valid** — "Generate quiz", "Submit answers", "Upload and extract skills", and "Approve and publish" are all correctly gated.
- **No unhandled console errors** on any page except the DOM-nesting warnings in C6 and the expected 501s.

---

## E. UI fixes, prioritised

### U0 — Blocking a usable product
1. **Expose a job listing to students** (A1) — wire `JobService.listActiveJobs(Pageable)` to a `GET /api/job-seekers/me/jobs` and render it on `/jobs` beneath the descope notice. Without this the employer role produces nothing.
2. **Add password reset** (B1) — requires B3 (email) or, as an interim, an admin-triggered reset in `/admin`.
3. **Add change-password** (B2) — one endpoint plus a card in each role's profile page.

### U1 — Correctness
4. **Filter consultation history** (C3) — add a date/status predicate to `getConsultationHistory`.
5. **Invalidate the history query after accept/reject/outcome** (C4).
6. **Enforce mentor availability at booking** (C1) — validate the requested slot against `ExpertAvailability`, and have `MentorsPage` offer the mentor's real slots instead of a free datetime input.
7. **Prevent double-booking** (C2) — unique constraint on (expert, datetime) plus an overlap check returning 409.
8. **Fix the match-score scale** (C5, `TASKS.md` T9).

### U2 — Fit and finish
9. **Fix the mobile overflow** on `/dashboard` and `/courses` (C7).
10. **Fix the invalid HTML nesting** (C6) — the `<p>` wrappers around `<details>`/`<ul>` should be `<div>`.
11. **Persist `targetedSkillName` and `explanation`** on `CourseRecommendation` (C8).
12. **Raise or measure `quiz-seconds` in prod** (C9).
13. **Route `StudyFieldPage`** and add its nav entry (A3).
14. **Surface the mentee skill dashboard to mentors** (A2).
15. **Add edit/delete for universities and study fields** (B4).
16. **Delete `PlaceholderHome.tsx`** (A4).

---

# Remediation Round — 2026-08-27

Everything below was verified by running it, not by reading the diff. Backend **230 tests pass
with no `JWT_SECRET` in the environment** (the CI scenario); frontend builds, 14 vitest tests
pass, lint clean apart from 4 pre-existing warnings.

## Build was broken on arrival

The backend did not compile. Three separate errors, none of which survive a `mvn test-compile`:

| File | Error |
|---|---|
| `GlobalExceptionHandler.java:30` | `@Slf4j` used without `import lombok.extern.slf4j.Slf4j;` |
| `LearningOutcomeReviewService.java:498` | `ai.getHttpStatus()` — the field is `status`, so Lombok generates `getStatus()` |
| `LearningOutcomeReviewServiceTest.java` | missing repository import; `.mapVersion(1)` where `Long` is required; `PublishLearningOutcomeRequest.builder()` on a DTO with no `@Builder` |

All five fixed. The new publish test additionally never stubbed the draft-revision CAS, so it
asserted `DuplicateResourceException` and got `StaleResourceException`; it now stubs the CAS and
drops two stubs that Mockito's strict mode rejected as unused.

## Fixed in this round

**Correctness**

- **Consultation history is now scoped** — `findUpcomingForExpert` / `findHistoryForExpert` are
  exact complements (future + live vs. past-or-terminal). A future request no longer appears in
  both lists. Verified live: `scheduled: [5], history: [], overlap: none`.
- **"Completed" is now a real status.** `submitConsultationOutcome` recorded notes and feedback
  but never changed the status, so `AppointmentStatus`'s documented `Completed` was dead
  vocabulary and a finished session sat in Upcoming forever. Recording an outcome now closes the
  session. Verified: `Requested → Accepted → Completed`, and it moves to history on completion.
- **Mentor availability is enforced at booking.** `ExpertAvailability` was write-only — a whole
  page of curated slots that nothing read. Booking now validates day and time against the
  published schedule (end exclusive), and a mentor with no schedule is not bookable at all.
  Verified: a Tuesday request against a Monday-only mentor returns 400 naming the real slots.
- **Double-booking is refused** — a non-rejected appointment holds the slot. Second identical
  request returns 409 instead of a third duplicate row.
- **Availability reaches the student.** `MentorSummaryResponse` now carries the slots, the
  mentors page renders "Available: Mon 09:00–17:00", disables Request for mentors with no
  schedule, and blocks submission of a time outside the published window before it is sent.
- **Session lists refresh after every mutation** — accept/reject/outcome each move an
  appointment between lists, so patching only the visible one left the other stale. Both are
  refetched.
- **Optimistic-lock collisions answer 409, not 500.** Concurrent writes were surfacing as
  "something went wrong on our end"; they are a conflict the caller can retry.
- **Recommendation reasoning is persisted** (`V6__persist_recommendation_reasoning.sql`). The
  targeted skill and explanation were discarded on save, so the courses page had to apologise
  and tell students to regenerate. Verified: 20 of 20 rows keep their reasoning on re-read.

**Security and operations**

- **Change password, for every actor** — `POST /api/auth/password`. Requires the current
  password (a stolen session must not be enough to take the account) and revokes the calling
  token on success. Reachable from all five profile screens; the administrator had no profile
  page at all, so `/admin/profile` was added — it was the most privileged account in the system
  and the only one that could not rotate its credential.
- **Login rate limiting** — `LoginRateLimitFilter`, keyed on client IP *and* actor route so one
  NAT cannot lock out an office and exhausting the admin route does not affect students. Only
  401s count; a success clears the counter. Verified: `401 ×10 → 429`, with other routes
  unaffected. In-process and per-instance by design — see the class Javadoc before scaling out.
- **Actuator health/metrics** — the Docker healthcheck probed `/v3/api-docs`, which returns 200
  while the database is unreachable. Only `health` and `info` are exposed; `/actuator/env`
  returns 401. Health is permitAll because a probe carries no credentials.
- **CORS is configurable** — `CORS_ALLOWED_ORIGINS`, replacing a hardcoded localhost list with a
  `TODO`.
- **Production quiz timeout raised to 90s.** It was 15s against a measured 25–70s generation, so
  every production quiz would have timed out mid-write.
- **`JWT_SECRET` in tests comes from the build**, not `src/test/resources/application.yml` — a
  test-classpath file of that name shadows the main config entirely and drops storage paths, AI
  timeouts and Flyway settings, failing in ways that look unrelated.

**Documentation and hygiene**

- **OpenAPI multipart contract fixed** — the learning-outcome upload documented only `file`
  while requiring three more form fields.
- **`DatabaseMigrationTest` no longer hardcodes a migration count** — it discovers the packaged
  chain, so adding a migration stops looking like a schema regression.
- **Invalid HTML nesting fixed** — `<details>`/`<ul>` inside `<p>` on the dashboard, which React
  flagged as a hydration hazard on every render.
- **Mobile overflow fixed** — the shared topbar forced every authenticated page sideways on a
  phone (`/dashboard` 443px, `/courses` 406px at a 375px viewport). Both now measure exactly 375.
- **Seeded mentors get a weekly schedule**, so enforcing availability does not leave the demo
  with a mentor list where every request is refused. Applies to fresh databases only.

## Still outstanding

- **Password reset (B1)** — the one item that cannot be finished as a code change. It needs a
  delivery channel, and the project has no mail capability at all (no `JavaMailSender`, no
  SMTP config). The options are an SMTP dependency or an admin-issued reset token handed over
  out-of-band; both are decisions about how the deployment works, not defects to patch. Change
  password (B2) is done, which covers rotation but not recovery of a forgotten credential.
- **Mentor match scores still do not discriminate** (C5) — 4 of 5 mentors score identically.
  The scoring lives in the AI service's `mentor_matching.py`, and `TASKS.md` T9 carries a
  warning to read first, so it deserves its own pass rather than being folded into this one.
- **Reference data is still create-only** (B4) — no edit or delete for universities and study
  fields, on either side.
- **Untouched from the deployment list**: CD pipeline, error tracking, structured logging,
  object storage for uploads, dependency/CVE scanning, coverage tooling, and the Spring Boot
  3.3.4 upgrade.
