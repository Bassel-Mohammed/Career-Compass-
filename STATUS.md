# CareerCompass — Project Status

**Date:** 25 August 2026
**Branch:** `integration/full-stack`
**Requirements:** 71 functional · 67 non-functional
**Contributors:** 4

> Coverage below describes **implemented and reachable code paths**, not formal acceptance.
> No functional requirement has been signed off against written acceptance criteria, and no
> performance, load or security testing has been run against the NFR budgets.

---

## Headline

Both backends are built and genuinely talk to each other. The browser interface is now usable for
authentication, the complete student journey, content-manager learning-outcome work, and the
employer job-posting workflow. Mentor and administrator workspaces still stop at guarded
placeholder landing pages.

The frontend is wired to the real Spring API and reports the current job/candidate matching
limitations instead of presenting placeholder scores as AI analysis. The mentor screen currently
uses Java's same-field listing rather than Python's new ranked matching endpoint. The frontend
builds and lints cleanly, but there is not yet an automated browser end-to-end suite.

---

## Where each part stands

| Component | State | Detail |
|---|---|---|
| Python AI service | **Built** | 18 `/api/v1` routes plus the root redirect. M1–M5 and M6 mentor matching are built and tested; job matching is descoped |
| Java backend | **Built** | 12 REST controllers, 63 mapped methods, 25 JPA entities. Every actor group covered |
| Java ↔ Python link | **Working** | 5 capabilities verified against the running service (was 0 of 6) |
| Frontend | **In progress** | React 19 + Vite; auth, 8 student routes, 2 content-manager routes, and the employer workspace are built; mentor/admin are placeholders |
| Development stack | **Configured** | Docker Compose runs frontend, Java, and Python with health checks, a shared service token, H2/JSON data, and persistent learning-outcome uploads; production databases are intentionally deferred |
| Docs & contract | **Current** | 8 ADRs, validated OpenAPI contract, database runbooks, and runtime plus MySQL/PostgreSQL migration CI |

---

## Frontend coverage

All actor pages are role-guarded in `frontend/src/App.tsx`; browser code calls Spring Boot only,
never the internal AI service directly.

| Surface | Routes | State |
|---|---|---|
| Public auth | `/login`, `/signup` | Built; all five actors can sign in, while only students and employers can self-register |
| Student | `/setup`, `/dashboard`, `/transcript`, `/courses`, `/quizzes`, `/jobs`, `/mentors`, `/profile` | Built in `frontend/src/pages/student/`; covers profile setup, transcript review/confirmation, skill dashboard, recommendations, quizzes, disclosed job matches, mentor booking, and account management |
| Employer | `/employer`, `/employer/jobs/new`, `/employer/jobs/:jobId/edit`, `/employer/jobs/:jobId/candidates`, `/employer/profile` | Built in `frontend/src/pages/employer/`; posting CRUD, company profile, and candidate ranking with explicit 501/mock-score disclosure |
| Content manager | `/content`, `/content/profile` | Built in `frontend/src/pages/content/`; study-field selection plus learning-outcome upload/list/file removal |
| Mentor | `/expert` | Placeholder landing page; availability, profile, and consultation screens are not routed yet |
| Administrator | `/admin` | Placeholder landing page; account and reference-data screens are not routed yet |

The API adapters live under `frontend/src/api/`, shared session/role guards under
`frontend/src/auth/`, and the reusable responsive shell and form/status components under
`frontend/src/components/`.

---

## Requirement coverage by actor

| Actor | Requirements | State | Notes |
|---|---|---|---|
| Job Seeker | `FR-JS-01…25` | 24 of 25 real | Backend and browser flows exist for auth, profile, transcript, dashboard, recommendations, quizzes, jobs, and consultations. **FR-JS-23** job matching is mock scoring only; mentor browsing is same-field rather than AI-ranked until Java calls the Python matcher |
| Employer | `FR-EMP-01…15` | API + browser workflow | Registration, login, company profile, posting CRUD, and candidate listing have UI. **FR-EMP-11/12** candidate ranking still returns mock scores with an explicit warning |
| Content Manager | `FR-CM-01…07` | Storage + browser workflow | Study-field selection and learning-outcome upload/list/file removal have UI. **FR-CM-04/05** uploaded PDFs are stored but never reach the AI service |
| System Admin | `FR-SA-01…11` | API only | Admin login and management APIs exist; the browser workspace is still a placeholder |
| AI internal | `FR-AI-01…14` | 11 of 14 | Extraction, vector, gap, recommendation, quiz, and mentor ranking are implemented. **FR-AI-12/13** job-matching directions remain unbuilt. **FR-AI-14** audit logging is partial |

---

## The six AI modules

| Module | Capability | State | Limiting factor |
|---|---|---|---|
| M1 | Transcript analysis | Built | — |
| M2 | Skill vector | Built | Deterministic, no model involved |
| M3 | Skill gap | Built | — |
| M4 | Course recommendation | Coverage-limited | Works correctly; the course catalog is thin |
| M5 | Quiz generation | Built | Answers checked structurally, not conceptually |
| M6 | Job matching | Descoped | Deferred by decision; 2,238 postings ready when picked up |
| M6 | Mentor matching | Python built; Java not wired | `POST /api/v1/mentor-matches` ranks caller-supplied mentors against student gaps; 19 matcher tests pass |

---

## Knowledge base coverage

For the implemented analysis and matching modules, answer quality is now limited mainly by the
coverage and specificity of their input data.

| Asset | Coverage | Note |
|---|---|---|
| Course syllabi extracted | **20 of 114** | The binding constraint — courses with no syllabus contribute nothing to a skill vector |
| Career-path requirements | 771 rows | All 9 paths, 82–105 skills each |
| Job postings | 2,238 | Skills extracted and matched |
| Skills taxonomy | 903 rows | Zero orphans |
| Online course catalog | Partial | Coursera + MIT Learn. Udemy impossible — affiliate API closed Jan 2025 |
| Mentor records | **5 in dev** | `DevDataSeeder` creates active examples; non-dev records are admin-managed. Python stores no catalog because callers supply candidates per request |

---

## What has actually been verified

Latest test runs on 25 August 2026 — measured, not estimated.

| Result | Meaning |
|---|---|
| **6 / 6** | Live cross-runtime tests passing — real Java client against real FastAPI, including an LLM-generated quiz |
| **193 total, 6 skipped** | Full Java suite: 0 failures and 0 errors; includes fresh and legacy Flyway upgrade tests |
| **199 passed** | Full Python suite: 0 failures, with 1 existing Starlette/httpx deprecation warning |
| **2 / 2** | Frontend production build and lint commands passing |
| **PostgreSQL restore rehearsal** | Verified backup restore, ordered 001–005 migration, checksum history, repeat no-op, row counts, and migration-004 backfill on a disposable copy |
| **Migration CI configured** | MySQL 8.4 fresh/V1-upgrade plus PostgreSQL 17 fresh/001–003-upgrade jobs; service-backed jobs run in GitHub Actions |
| **Compose static validation** | Service wiring, ports, health checks, shared token, and upload volume checked; image build/start still requires a machine with Docker installed |
| **0** | Endpoints returning 404 or 422. Previously all six did |

---

## What is blocking, in order

Ordered by what stops the project being demonstrable, not by effort.

### 1. Mentor and administrator browser workflows are missing — HIGH

Student, employer, and content-manager workflows are demonstrable in the browser. Mentor and
administrator users can authenticate, but their home routes render `PlaceholderHome` and the
deeper destinations shown in their navigation are not registered yet. There is also no automated
browser end-to-end coverage for the workflows that are built.

### 2. Only 20 of 114 course syllabi are extracted — CRITICAL

A student whose courses have no extracted syllabus gets a thin skill vector and a dashboard that
understates them. The service reports this honestly rather than hiding it, but the fix is
collection work, not code.

### 3. Production database rollout still needs an operator-approved window

The repository paths are now automated: Java uses a tested Flyway V1–V4 chain followed by
Hibernate validation, and Python packages an ordered PostgreSQL 001–005 runner with advisory
locking and immutable checksums. PostgreSQL migrations 004/005 passed against a restored copy,
but the configured live AI database remains unchanged until the operator explicitly approves the
live mutation. The MySQL service-backed verification is configured in CI and should be observed
green before a production backend baseline/upgrade.

---

## Recommended order of work

1. **Build the mentor and administrator workspaces** and add browser-level tests for the critical
   registration → transcript → dashboard and employer posting flows.
2. **Keep collecting syllabi.** Steady background work that directly improves every dashboard,
   recommendation and quiz the system produces.
3. **Run the database rollout gates:** observe both migration CI jobs, explicitly baseline any
   reviewed legacy MySQL schema at V1, and schedule the rehearsed live AI migration with a rollback
   owner and the verified backup available.
4. **Then reconsider job matching.** The data is ready and the plan is written. Mentor matching's
   next steps are Java integration and collecting explicit expertise terms; until then its Python
   fallback uses reviewed study-field-to-career-path inference and labels that signal honestly.

---

## Sources

- `docs/compatibility/CareerCompass_Java_Python_Compatibility_Report.md` — audit
- `docs/compatibility/JAVA_PYTHON_INTEGRATION_FIX_PLAN.md` — remediation plan, §16 status
- `docs/contracts/careercompass-ai-internal-v1.yaml` — the Java ↔ Python contract
- `docs/adr/` — ADR-001…008
- `ai-service/docs/PROJECT_STATUS.md` — AI module and knowledge-base state
- Planning baseline: `/home/almadhoun/Desktop/CareerCompass`
