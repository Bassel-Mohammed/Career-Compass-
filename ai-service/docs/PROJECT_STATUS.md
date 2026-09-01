# CareerCompass Implementation Status

Where the code stands against the Knowledge Base and six AI modules of
Section 5.3 of the project report.

**Last updated:** 25 August 2026

Cross-cutting engineering facts — the identity defects, silent-failure modes,
measured numbers, hardware constraints and open decisions — are in
[ENGINEERING_NOTES.md](ENGINEERING_NOTES.md). This page is only the build state.

**Legend:** ✅ built · 🟡 partial · ❌ not started

## Modules

| Piece | Status |
|---|---|
| M1 Transcript analysis | ✅ `parsing/transcript.py` + `parsing/grades.py`, exposed at `POST /api/v1/transcripts/parse` |
| M2 Skill vector | ✅ `skills/vector.py` — deterministic, quiz override, 39 tests |
| M3 Skill gap | ✅ `skills/gap.py` — three-valued classification, demand-weighted priority, 49 tests |
| M4 Course recommendation | 🟡 `skills/recommend.py` + `catalog/` — built and working; catalog coverage is the limit |
| M5 Quiz | ✅ `skills/quiz.py` — generation, validation, self-check, programmatic grading, 74 tests |
| M6 Mentor matching | ✅ `skills/mentor_matching.py`, exposed at `POST /api/v1/mentor-matches` — deterministic, ranked against gaps rather than strengths, 19 tests (ADR-008) |
| M6 Job matching | ❌ Not started. Unblocked — 2,238 postings with per-posting skills already exist; descoped by owner decision, not by obstacle |
| FastAPI layer | ✅ 19 endpoints; M2–M6 mentor all exposed |
| Service authentication | ✅ `api/auth.py` — bearer token on `/api/v1/*`, health exempt. Off unless `CC_SERVICE_TOKEN` is set, and says so at startup |

## Knowledge base

| Piece | Status |
|---|---|
| Course → skill map (real syllabi) | 🟡 20 of 114 courses; 20 PDFs collected |
| Course → skill map (synthetic) | ✅ 96 courses under `data/mock/` — testing only, never production |
| Job catalog | ✅ 2,238 postings across 9 career paths, skills extracted and matched |
| Career-path → required-skills ontology | ✅ 771 requirements, 82–105 per path, now carrying `skill_type` |
| Skills taxonomy | ✅ 903 rows, 0 orphans |
| Online course catalog | 🟡 Coursera + MIT Learn ingested. **Udemy is not possible** — its Affiliate API was discontinued 1 January 2025 |
| Mentor expertise data | 🟡 Mentors are supplied per request by the caller, so no catalog is needed here. But an expert record carries only a study field, so ranking falls back to a **reviewed** study-field→career-path mapping and reports `signal: inferred`. Collecting expertise terms in Java is the single biggest quality win, and the contract already accepts them |

## What is not verified

Worth stating plainly, because none of it fails loudly:

- **Migrations 004 and 005 are rehearsed but not yet applied live.** A verified
  custom-format backup was restored to a disposable PostgreSQL database. The
  packaged runner adopted 001–003, applied 004/005, recorded all five SHA-256
  checksums, passed a repeat no-op, preserved row counts, and backfilled all
  771 career-path rows without a taxonomy mismatch. Live execution requires a
  separate operator-approved change window.
- **YouTube ingestion has only been exercised on its no-key path.** It needs
  `CC_YOUTUBE_API_KEY`; without one it is skipped with a warning rather than
  failing the run.
- **Quiz answer keys are only structurally checked.** A question can be
  well-formed, self-consistent and still conceptually wrong — see
  ENGINEERING_NOTES §14.

## The critical path

Two different coverage problems, and they are not the same shape.

**Student side.** Real syllabi exist for 20 of 114 courses.
`data/plans/required_syllabi.md` tracks the collection across all four majors
and regenerates from disk:

```bash
python -m careercompass.cli.build_syllabus_list
```

Synthetic rows fill the gap so M2, M3 and M5 could be built and verified. They
must never reach the production `course_skills` table — ENGINEERING_NOTES §10.

**Recommendation side.** M4 can only recommend what the catalog contains, and
unlike the student side this gap **cannot be filled synthetically**: a course
that does not exist is a dead link the student clicks. `skills_without_courses`
in every recommendation response names the requirements the catalog cannot yet
serve.

## Next

1. **Decide the canonical course id** before more syllabi are extracted;
   retrofitting means re-extracting everything. ENGINEERING_NOTES §3.
2. **M6, job half** — the data is real and already in place.
3. **Collect the remaining real syllabi** — the long pole, dependent on others.
4. **Schedule the rehearsed live 004/005 upgrade** with the verified backup and
   an explicit operator approval; do not rely on automatic startup migration.
5. **Tell the backend owner about the contract mismatch.** Five of his six
   endpoints do not exist, and there are now four working ones he does not know
   about. ENGINEERING_NOTES §12b.

## Interfaces

| Document | Covers |
|---|---|
| [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md) | how the system actually behaves, and why |
| [API_DESIGN.md](API_DESIGN.md) | platform-wide interface: five actors, all six modules |
| [SKILL_EXTRACTION_API.md](SKILL_EXTRACTION_API.md) | the skills subsystem, as implemented |
| [SYLLABUS_SKILL_EXTRACTION.md](SYLLABUS_SKILL_EXTRACTION.md) | syllabus pipeline internals |
| [JOB_SKILL_EXTRACTION.md](JOB_SKILL_EXTRACTION.md) | job pipeline internals |
