# Project Test Report

**Date:** 21 August 2026
**Scope:** CareerCompass end to end — parsing, skills (M1–M5), catalog, API, CLI, db, data artefacts
**Tested by:** QA pass against a live instance, not a code read alone

---

## Executive Summary

CareerCompass is a **well-engineered service with an unusually honest codebase**. The
error contract is real RFC 9457 and it holds on almost every path. The async job design
is correct and validated by measurement. M2 and M3 are byte-for-byte deterministic. The
shared matcher survived every concurrency attack I made on it. All ten test suites pass,
719 checks.

It is also **not ready to sit behind a backend as-is**, for four reasons that the
existing documentation does not cover:

1. A **354 KB PDF kills the process** (decompression bomb, no ratio guard). During this
   test run it took out *both* running instances via the OOM killer.
2. The JSON artefacts every API path reads still contain **retired skill ids**
   (`custom:java`, `custom:python`). A student who passed *Object Oriented Programming in
   Java* with an **A** is told Java is a complete gap. `remap_retired_skills` repaired the
   database; nobody repaired the files the API actually serves from.
3. The LLM stage **accepts confidently wrong matches at 0.95**. An Operating Systems
   syllabus saying "process … synchronization … and communication" is credited with
   `communication skills` — an interpersonal soft skill in the top three of nearly every
   career path. "Monitors" (the OS concurrency primitive) becomes
   `monitoring and observability`.
4. A malformed PDF — the most common bad input there is — returns **HTTP 500**, directly
   contradicting the design note in `app.py` that says parsing exists so malformed
   documents can be reported as 4xx.

| | |
|---|---:|
| Test suites run / passed / failed | 10 / 10 / 0 |
| Individual checks in those suites | **719 passed**, 0 failed |
| Additional tests executed by hand | **147** |
| Passed | 121 |
| Failed (defects) | 26 |
| Blocked / not tested | 11 areas |
| **New bugs confirmed** | **27** |
| Critical | 1 |
| High | 4 |
| Medium | 14 |
| Low | 8 |
| Already-documented limitations hit | 8 |

**Risk level: HIGH** — driven by one availability defect (bomb), one silent data-corruption
defect (retired ids), and one silent-wrongness class (accepted bad matches). Everything
else is ordinary hardening.

---

## Remediation Status — 21 August 2026

The findings below are the record of the test pass and are left as written. This
section records what has since been fixed, so the two can be told apart.

**Fixed and verified** (suite now 781 checks, up from 719; all ten pass):

| ID | Fix | Verified by |
|---|---|---|
| **CC-01** | New `parsing/pdf.py` bounds the **decompressed** content stream (16 MB), page count (200) and extracted glyphs (2 M) before any layout object is built. The upload limit bounded the compressed size, which is the wrong number. | 354 KB bomb → **422 in 0.10 s**, was OOM-kill. Bounded repro under `RLIMIT_AS` raises `ValueError`, was `MemoryError` after 12 s |
| **CC-02** | `cli/remap_extracted_skills.py` repaired the 5 stale rows; `vector.load_course_skills` now resolves every id through the alias index at load and logs on a miss. ENGINEERING_NOTES §2 documents the merge as three steps. | A grade of **A** in `0412201` now reads `Java: strong`, was `weak / 0.0`. Real student's Python moved from **rank 1 at 0.00** to rank 9 at 0.50 |
| **CC-03** | The same module converts `PdfminerException` → `ValueError`, which every caller already maps correctly. One site fixed both parsers, three endpoints and two CLIs. | Corrupt / empty / non-PDF → **422** on both endpoints, was 500. Both CLIs exit 1 with `❌ Error:`, **0 tracebacks** |
| **CC-04** | Three guards, applied at *both* accept points: a `soft` skill is never auto-accepted from a syllabus phrase; a generic single word whose evidence only restates it is never auto-accepted; the noise filter now runs inside `SkillMatcher.match`, and `development`/`automation`/`activities` were added to `NOISE_TERMS`. 45 already-stored wrong accepts were demoted by the repair CLI. | `communication`, `Monitors`, `Performance` → `needs_review`; `automation`, `presentation` → `no_match`. Controls `Kinematics` (with real evidence), `Kubernetes`, `motion planning` **stay accepted** |
| **CC-14** | Folded into the CC-04 work and listed here so it is not lost: `development`, `automation` and `activities` — the three words §5 opens with — are now in `NOISE_TERMS`, and the filter runs inside `SkillMatcher.match` rather than only in `extract_skills`, so `POST /api/v1/skills/match` can no longer bypass it. | `automation`, `presentation`, `development`, `activities` → `no_match` / `noise_filter` on the ad-hoc endpoint, were accepted at 0.95 / 0.633 |
| **CC-05** | `LEVEL_COVERAGE` gate in `gap.py`: `strong` now needs both proficiency *and* evidence. Rows carry `evidence_coverage` and `required_coverage`. | Two-course profile: **12 strong → 3**. `monitoring and observability` and `performance testing` both left `strong` |
| **CC-06** | `quiz_scores` bounded to 0.0–1.0 in the schema; unknown skill ids now 404. | `85` → **422**, was 200 with proficiency silently clamped to 1.0 |
| **CC-08** | `POST /api/transcript/upload` and `GET /api/health` deleted, with `shutil`/`HTTPException` imports. | Both → 404; `/api/v1/health/live` unaffected |
| **CC-19** | Parse failures now name the caller's file, not the server's temp path. | 0 `upload_*` occurrences in error details |
| **CC-20** | Shadowed `skill_ids` parameter in `build_index` renamed. Two more of the same shape were found and fixed in the new code while writing it. | — |

**Second pass — the seven you picked next** (suite now **808 checks**):

| ID | Fix | Verified by |
|---|---|---|
| **CC-16** | `SkillGapResponse` and `RecommendationResponse` now carry `courses_counted` and `courses_skipped`, via one `_with_coverage` helper. | Real transcript gap now reports `courses_counted: 7, courses_skipped: 67` with reasons `{no skill map: 48, not passed: 19}` — was silent |
| **CC-15** | `_no_profile_detail` derives the message from the actual per-course reasons, and the Problem carries `courses_skipped`. | An F grade now reads *"of 2 submitted courses, 1 was not passed, so it carries no credit, and 1 has no extracted syllabus yet"* — was "None … have an extracted skill map" for a course with 84 skills |
| **CC-27** | `TRANSFER_STATUSES` separates credit-without-a-mark from not-completed. Two denominators: `coverage` counts transfer credit, `graded_coverage` is what the proficiency mean divides by, so an unmarked course can no longer average in as a zero. New `graded_coverage` field and `evidence: "transfer"`. | Mixed profile keeps `proficiency 1.0` where it was diluted to 0.0. Real transcript surfaces **5 skills that were previously invisible** (SQL, C#, data models…); "not passed" fell 39 → 19 |
| **CC-12** | `skills_without_courses` is now `[{skill_id, skill_label}]`, deduplicated. | `esco:1d86f05e-…` now reads `solution deployment` |
| **CC-07** | `psycopg2.errors.ForeignKeyViolation` caught per decision into the existing `errors[]`. | Bad id → **200** `{"recorded":1,"errors":[{"error":"'not:a:skill' is not in the taxonomy"}]}` — was 503 "Database is unreachable" with the constraint name leaked, aborting the batch |
| **CC-13** | `validate_question` gains cross-question checks: an identical normalised **option set**, or question text over `QUESTION_SIMILARITY` (0.70). | Replaying the four real captured quizzes: **Docker 5 → 2**, **SQL 5 → 2**, while **Git 4 → 4** and **cryptography 5 → 5** are untouched — the redundant ones only |
| **CC-11** | `allow_origins` is a named list from `CC_API_CORS_ORIGINS`, `allow_credentials=False`, methods narrowed. | A foreign `Origin` now gets **no CORS headers**; `http://localhost:3000` is allowed |

**Not regressed after either pass:** M2/M3/M4 remain **byte-identical** across repeat calls;
concurrent requests return one distinct body per endpoint; the bomb, corrupt uploads, the
deleted legacy route and the `quiz_scores` bound all still behave.

**One judgement left open by CC-27.** A skill evidenced *only* by transfer credit now has
`coverage > 0`, `graded_coverage = 0`, `evidence: "transfer"` and `proficiency: 0.0` — so
the gap still classifies it `weak`. The data to tell "studied, unmarked" from "never
studied" is now all present on the row (`SQL` reads `evidence='transfer',
evidence_coverage=0.85`; `CI/CD pipelines` reads `evidence=None, evidence_coverage=0.0`),
but whether M3 should treat an unknown mark differently from a zero is a product decision,
not a bug fix, and it was not made here.

**Deliberately still open** — everything in P1–P3 not listed above, most notably:

- **The `generative AI` alias** on `custom:large-language-models` still recommends
  *"Introduction to Generative AI in Legal"* for an LLM gap. Fixing it means editing
  `custom_skills.json` and rebuilding the taxonomy and vector index — wider blast radius
  than this pass allowed.
- CC-09, CC-10, CC-17, CC-18, and CC-21 through CC-26.

**One measured trade-off worth a decision.** The CC-04 guards demoted **45 of 455**
accepted rows (9.9%) to `needs_review` — chosen over a blanket single-word rule that would
have demoted 70 (15.4%) including correct matches like `Kinematics`→robot kinematics. Of
the 45, roughly half were plainly wrong (`Classical`→scikit-learn, `outlines`→dies,
`Architecture`→**robotics** system architecture in a *software* architecture course) and
the rest are defensible matches now awaiting a human (`oral presentations`→communication
skills, `dynamics`→robot dynamics). That is review-queue volume traded for not silently
crediting a student with a skill they never studied — consistent with the design's own
rule that "a needs_review row is a question, not a fact about a student" — but the
thresholds deserve tuning against the labelled set rather than staying as first cuts.

---

## Testing Environment

| | |
|---|---|
| OS | Linux 7.0.0-30-generic, x86-64 |
| Python | **3.14.4** (`pyproject.toml` requires ≥3.10) |
| Virtualenv | `.venv/` |
| `semantic` extra | **installed** — sentence-transformers 5.7.0, torch 2.13.0+cu130 |
| `llm` extra | **not installed** — `anthropic` absent (Anthropic path is code-review only) |
| Retrieval backend | **BGE — `st:BAAI/bge-m3`**, 903 entries (`CC_EMBEDDING_BACKEND=bge`) |
| Reranker | **lexical** (`CC_RERANKER=lexical`) → thresholds `accept=0.62`, `review_floor=0.40`, `margin=0.05` |
| LLM | **Ollama `qwen3:8b`, present and reachable**, `temperature=0` for matching |
| Other Ollama models | `qwen3:4b-instruct-2507-q4_K_M`, `llama3.2:3b` (not used — §8 says 4b auto-accepts bad matches) |
| PostgreSQL | **PRESENT AND REACHABLE** — `career_compass` @ localhost:5432 |
| Migrations applied | 001, 002, 003 |
| Migrations **not** applied | **004** (no `career_path_skills.skill_type` column), **005** (no `catalog_courses`, no `catalog_course_skills`) |
| GPU | RTX 4060 Laptop, 8188 MiB |
| RAM | 15176 MB total |

> **Deviation from the brief worth stating up front.** The brief says "No PostgreSQL is
> available." That is no longer true — a populated database is configured and reachable
> (903 taxonomy skills, 2,238 `linkedin_jobs`, 175,623 `job_skills`, 771
> `career_path_skills`, 308 `course_skills`). I therefore tested the DB layer live rather
> than by reading only, and **restored every row I wrote**. Migrations 004 and 005 remain
> unapplied, exactly as documented.

**Backend attribution.** Every matcher score in this report was produced by
**BGE retrieval + lexical reranker + qwen3:8b**, unless the line says otherwise. The one
important exception is `tests/test_skill_matcher`, which builds its own **lexical** test
index — see [Model-Dependent Behavior](#model-dependent-behavior).

---

## Test Coverage

| Area | Depth | What was actually done |
|---|---|---|
| **M1 Transcript** | Deep | Real 74-course academic plan through the API; all 6 grade/status classes; corrupt, empty, no-text, wrong-document inputs; CLI equivalents |
| **Parsing (syllabus)** | Deep | 3 real syllabi parsed; 5 hand-built malformed PDFs; warning propagation; temp-file cleanup verified |
| **Matcher (RAG)** | Deep | 10 hand-chosen phrases with known correct answers through the live BGE+LLM path; noise-term probes; all 20 stored artefacts audited for generic terms |
| **M2 Skill vector** | Deep | Determinism (byte-diff ×2); grade→attainment for A/B-/C/D-/F/None; transferred & exempted handling; `include_unpassed`; quiz override incl. out-of-range and unknown ids |
| **M3 Skill gap** | Deep | Determinism; all 9 career paths enumerated; `include_soft`; classification arithmetic traced against source syllabus evidence; response-field audit |
| **M4 Recommendations** | Deep | Determinism; **all 10 returned URLs fetched — 10/10 live**; relevance/level-fit inspected; `skills_without_courses` audited; catalog index diffed against the pre-fix version |
| **M5 Quiz** | Deep | 4 quizzes generated on the live LLM (Git, Docker, SQL, cryptography); **19 answer keys graded by hand**; cross-question redundancy measured numerically |
| **M6 Job/mentor matching** | Not started upstream | Ontology arithmetic verified against `career_path_skills.json`; no matching code exists |
| **API — all 19 endpoints** | Deep | Valid path + 61 negative cases: missing/wrong-type/out-of-range fields, unknown ids, oversized upload, wrong content type, malformed JSON, traversal attempts |
| **Extraction jobs** | Deep | Full lifecycle: submit → poll → succeed; idempotency; `force`; cancel; 409 on finished; 404 shapes; `store=true` against a live DB |
| **Review queue** | Deep | Fetch, filter, limits; valid/duplicate/malformed/FK-violating decisions |
| **CLI** | Deep | All 10 entry points load; the 2 parsers exercised with real/missing/non-PDF/corrupt/empty/no-text files |
| **Catalog** | Medium | Code review + no-key YouTube path; index rebuild verified by diff. **No network ingestion run** |
| **db/** | Medium | Live read/write/rollback; full SQL-construction audit; migration state |
| **Data artefacts** | Deep | Taxonomy orphans/duplicates/qualifier collisions; ontology↔taxonomy↔catalog↔course-artefact cross-joins |
| **Security** | Deep | Decompression bomb, traversal, size limits, secrets, CORS, SQL construction |
| **Performance** | Deep | Warm-up ×3, per-endpoint p50/min/max, per-request I/O cost, RSS, 30-way concurrency |

---

## Test Results

| ID | Area | Test | Result | Severity | Notes |
|---|---|---|---|---|---|
| T-01 | Suites | All 10 self-checking suites | ✅ PASS | — | 719 checks, 0 failures |
| T-02 | API | Warm-up: `/health/live` during build | ✅ PASS | — | 200 in 1.0–1.7 ms while warming |
| T-03 | API | `/health/ready` 503 + `Retry-After` while warming | ✅ PASS | — | Correct, per design |
| T-04 | API | Warm-up completes | ✅ PASS | — | **13.33 s / 13.51 s (GPU), 9.56 s (CPU)** — cached index |
| T-05 | API | 19 routes exposed | ✅ PASS | — | Matches the stated count exactly |
| T-06 | M1 | Real 74-course plan parsed | ✅ PASS | — | 0.26 s; 74 courses; GPA 2.75 computed vs 2.84 reported, both surfaced |
| T-07 | M1 | `save` defaults to false | ✅ PASS | — | `saved_to: null` — correct privacy default |
| T-08 | M2 | Determinism ×2 | ✅ PASS | — | Byte-identical |
| T-09 | M3 | Determinism ×2 | ✅ PASS | — | Byte-identical |
| T-10 | M4 | Determinism ×2 | ✅ PASS | — | Byte-identical |
| T-11 | M4 | Every returned URL resolves | ✅ PASS | — | **10/10 HTTP 200** on live Coursera |
| T-12 | Matcher | Exact-alias hits correct | ✅ PASS | — | Kubernetes, React.js, unit testing → right ids at 1.000 |
| T-13 | Concurrency | 24× parallel `/skills/match` | ✅ PASS | — | 24/24 × 200; **1 distinct result signature** — thread-safe |
| T-14 | Concurrency | 30× parallel M2/M3/M4 | ✅ PASS | — | 30/30 × 200; 1 distinct body per endpoint |
| T-15 | Jobs | Idempotency (same file, no force) | ✅ PASS | — | 200 + same `extraction_id` in 4 ms |
| T-16 | Jobs | `force=true` | ✅ PASS | — | 202 + new id |
| T-17 | Jobs | Cancel running job | ✅ PASS | — | Reaches `cancelled`, `result: null` |
| T-18 | Jobs | Cancel finished job | ✅ PASS | — | 409 `extraction-not-cancellable` |
| T-19 | Jobs | `store=true` against live DB | ✅ PASS | — | 21 rows written, 5 with `skill_id` |
| T-20 | Jobs | Full pipeline re-run vs stored artefact | ✅ PASS | — | **0 of 21 decisions changed** — LLM path stable at temp 0 |
| T-21 | Errors | 61 negative cases return Problem shape | ⚠️ MOSTLY | Low | 58/61 correct; 3 escape (T-36, T-38, T-41) |
| T-22 | Security | Upload size limit (25 MB) | ✅ PASS | — | 413 on v1 endpoints |
| T-23 | Security | Path traversal on `course_code` | ✅ PASS | — | Regex-guarded + router-normalised |
| T-24 | Security | SQL construction audit | ✅ PASS | — | Fully parameterised; the one f-string interpolates a hard-coded table tuple |
| T-25 | Security | DB password in responses/logs | ✅ PASS | — | 0 occurrences across all endpoints and logs |
| T-26 | Data | Taxonomy duplicates / orphans | ✅ PASS | — | 903 skills, 0 dup ids, 0 dup labels, **0 qualifier-stripped collisions** (§2 fix holds) |
| T-27 | Data | Ontology arithmetic | ✅ PASS | — | 771 rows, 0 coverage outside 0–1, **0 rows at >0.99** (§2 union fix holds) |
| T-28 | Catalog | Uncommitted `course_index` fix | ✅ PASS | — | CSS 0→277, NoSQL 0→78, Ansible 0→69, Metasploit 0→17, Xcode 0→24; index 162→187 skills |
| T-29 | **Security** | **PDF decompression bomb** | ❌ **FAIL** | **Critical** | **CC-01** — 354 KB → 12.4 GB RSS, both servers OOM-killed |
| T-30 | **Data** | Retired skill ids in served artefacts | ❌ **FAIL** | **High** | **CC-02** — `custom:java` ×4, `custom:python` ×1 |
| T-31 | **API** | Corrupt / non-PDF upload | ❌ **FAIL** | **High** | **CC-03** — HTTP 500, not 4xx |
| T-32 | **Matcher** | Known-wrong matches accepted | ❌ **FAIL** | **High** | **CC-04** — 3 confirmed at 0.95, stored and propagating |
| T-33 | **M3** | Classification ignores `coverage` | ❌ **FAIL** | **High** | **CC-05** — one word + grade A = "strong" |
| T-34 | M2 | `quiz_scores` range unvalidated | ❌ FAIL | Medium | **CC-06** — 85 silently → 1.0 |
| T-35 | Review | Bad `skill_id` → 503 | ❌ FAIL | Medium | **CC-07** — client error as outage; partial commit |
| T-36 | Legacy | `/api/transcript/upload` | ❌ FAIL | Medium | **CC-08** — 4 defects in one endpoint |
| T-37 | CLI | `build_syllabus_list --help` writes | ❌ FAIL | Medium | **CC-09** — destructive `--help` on a tracked file |
| T-38 | CLI | `cc-parse-transcript` | ❌ FAIL | Medium | **CC-10** — always saves PII; exits 0 on non-plan |
| T-39 | Security | CORS | ❌ FAIL | Medium | **CC-11** — echoes any Origin + credentials |
| T-40 | M4 | `skills_without_courses` unusable | ❌ FAIL | Medium | **CC-12** — bare ESCO UUIDs |
| T-41 | M5 | Quiz question redundancy | ❌ FAIL | Medium | **CC-13** — 4/5 questions, one fact |
| T-42 | Matcher | `/skills/match` has no noise filter | ❌ FAIL | Medium | **CC-14** — §5's own three examples unfiltered |
| T-43 | API | `no-skill-profile` detail is wrong | ❌ FAIL | Medium | **CC-15** — names the wrong reason |
| T-44 | M3/M4 | Coverage caveat dropped from response | ❌ FAIL | Medium | **CC-16** — consumer cannot see 30 skipped courses |
| T-45 | Privacy | gitignore gap on saved transcripts | ❌ FAIL | Medium | **CC-17** — client-chosen filename escapes the rule |
| T-46 | Runtime | FAILED matcher never re-warms | ❌ FAIL | Medium | **CC-18** — transient OOM bricks the instance |
| T-47 | API | Temp filename leaked in error detail | ❌ FAIL | Low | **CC-19** |
| T-48 | Code | `build_index` shadows its parameter | ❌ FAIL | Low | **CC-20** |
| T-49 | API | Routing 404s bypass Problem shape | ❌ FAIL | Low | **CC-21** |
| T-50 | Security | `/health/ready` leaks DB host:port | ❌ FAIL | Low | **CC-22** |
| T-51 | Perf | Per-request re-parsing of 14.2 MB | ❌ FAIL | Low | **CC-23** — 83.5 ms/call, 71 MB peak |
| T-52 | M4 | Unknown `skill_id` filter → 200 empty | ❌ FAIL | Low | **CC-24** |
| T-53 | API | `health()` mislabels LLM as failed | ❌ FAIL | Low | **CC-25** |
| T-54 | Docs | Four factual inaccuracies | ❌ FAIL | Low | **CC-26** |
| T-55 | M2 | Transferred-credit handling ≠ comment | ❌ FAIL | Medium | **CC-27** |

---

## Bugs & Reproduction Steps

Every bug below was reproduced. Environment for all: **BGE retrieval + lexical reranker +
qwen3:8b LLM ON + PostgreSQL present**, unless stated.

---

### CC-01 — PDF decompression bomb exhausts memory and kills the process
**Severity: CRITICAL** · Module: `parsing/syllabus.py`, `parsing/transcript.py`, all four upload endpoints, both parser CLIs · **Reproduced: yes, twice**

A 354 KB PDF passes the 20 MB size check and expands to over 12 GB during text extraction.

**Reproduce — build the bomb:**
```python
import zlib
raw = (b"BT /F1 8 Tf 10 700 Td (AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA) Tj ET\n") * 1_500_000
comp = zlib.compress(raw, 9)      # 106 MB -> 353 KB, ratio 295:1
# wrap `comp` as a single /FlateDecode content stream in a 1-page PDF -> bomb.pdf (354 KB)
```
```bash
curl -X POST http://127.0.0.1:8000/api/v1/syllabi/preview -F "file=@bomb.pdf"
```

**Expected:** 413, or a 422 after a bounded amount of work.
**Actual (run 1, live server):** RSS climbed 2,534 MB → **12,354 MB**; the kernel OOM
killer terminated the target server *and* a second, unrelated CareerCompass instance on
another port. No HTTP response was ever returned.

**Actual (run 2, bounded reproduction under a hard 2 GB `RLIMIT_AS`):**
```
notext.pdf    0 KB on disk -> OK, 0.0 MB text in 0.0s
bomb.pdf    354 KB on disk -> MemoryError: blew the 2 GB cap after 12.0s
```

**Root cause:** `_read_pdf` bounds the *compressed* upload only. `pdfplumber.open()` /
`extract_text()` then decompress without any ratio cap, page cap, character cap or
timeout. The 20 MB limit gives false confidence — it bounds the wrong number.

**Why it matters beyond one request:** the process is shared. One bad upload takes down
every in-flight extraction, the in-memory `JobStore` (all job history is lost — it does
not survive a restart, by design), and any co-resident instance.

**Suggested fix:** in `_read_pdf`, and in both parsers, enforce (a) a decompressed-size
budget — abort past ~50 MB of extracted text, (b) a page-count cap, (c) a wall-clock
timeout on `to_thread` parse calls. Cheapest first cut: check
`len(page.chars)` per page and bail past a threshold. Consider parsing in a
`resource.setrlimit`-capped subprocess so a bomb kills a worker, not the server.

---

### CC-02 — Retired skill ids in the artefacts the API actually reads
**Severity: HIGH** · Module: `data/extracted/skills/*.json`, `skills/vector.py`, `skills/gap.py` · **Reproduced: yes**

`ENGINEERING_NOTES` §2 records the 18 August Java merge and states that
`db.skills.remap_retired_skills` repoints stored rows. It repointed **the database**. The
**JSON artefacts** — which `PROJECT_STATUS.md` says *"Every API path reads … instead"* —
were never remapped.

**Reproduce:**
```bash
.venv/bin/python -c "
import json,glob
from careercompass.skills.taxonomy import load_taxonomy
known={s['id'] for s in load_taxonomy().skills}
for f in sorted(glob.glob('data/extracted/skills/*.json')):
    d=json.load(open(f))
    for s in d['skills']:
        m=s.get('match') or {}
        if m.get('canonical_id') and m['canonical_id'] not in known:
            print(d['course_code'], repr(s['term']), '->', m['canonical_id'], m['review_status'])"
```
**Actual:**
```
0412201 'Java'                -> custom:java   accepted      (weight 0.8)
0412201 'JAVA Basic elements' -> custom:java   needs_review
0412201 'JAVA Console Input'  -> custom:java   needs_review
0412201 'JAVA Program Style'  -> custom:java   needs_review
0434402 'Python'              -> custom:python accepted      (weight 0.7)
```
Live taxonomy ids are `esco:19a8293b-…` (Java) and `esco:ccd0a1d9-…` (Python).
Database check: `course_skills` and `taxonomy_skills` contain **zero** stale rows — the DB
was repaired, the files were not.

**End-to-end consequence, reproduced:**
```bash
curl -X POST .../api/v1/skill-gap -d '{"courses":[{"course_code":"0412201",
  "course_name":"OOP in Java","grade":"A","status":"passed"}],
  "career_path":"Backend Development"}'
```
```
Java    classification=weak  current=0.0  gap=0.85  importance=0.2717
Python  classification=weak  current=0.0  gap=0.85  importance=0.3587
```
The skill vector shows `custom:java` at proficiency **1.0**. The gap shows Java as a
**complete gap**, because the ontology keys on the ESCO id. This is precisely §2's stated
failure — *"every one made a student look like they lacked something they had"* — still
live. Python is the **#1 requirement of the AI & ML path (46%)**; a student who passed the
Python course is told it is their #2 priority gap.

**Suggested fix:** run the alias-remap over `data/extracted/skills/*.json`, not just the
DB, and make it part of the merge procedure. Better: have `load_course_skills` resolve
every `canonical_id` through the taxonomy's alias index at load time and **log loudly** on
a miss, so a retired id can never be silently dropped again.

---

### CC-03 — Malformed PDF returns 500 instead of 4xx
**Severity: HIGH** · Endpoints: `/api/v1/syllabi/preview`, `/api/v1/transcripts/parse`, `/api/v1/extractions`; also both parser CLIs · **Reproduced: yes**

```bash
printf 'this is plain text, not a pdf\n' > notreally.pdf
curl -X POST .../api/v1/syllabi/preview -F "file=@notreally.pdf"
# -> 500 {"type":"internal-error","title":"Unexpected server error","status":500}

head -c 400 real.pdf > corrupt.pdf; head -c 2000 /dev/urandom >> corrupt.pdf
curl -X POST .../api/v1/transcripts/parse -F "file=@corrupt.pdf"
# -> 500
```
**Expected:** 422 `unparseable-syllabus` / `unparseable-transcript`.

**Root cause** (server log):
```
pdfplumber.utils.exceptions.PdfminerException: No /Root object! - Is this really a PDF?
  File "src/careercompass/api/app.py", line 206, in _parse_transcript_bytes
    return parse_academic_plan(str(temp_path))
```
`_parse_pdf_bytes` and `_parse_transcript_bytes` catch **only `ValueError`**.
`PdfminerException` is not a `ValueError`, so it escapes to `unhandled_handler`.

This contradicts the module's own docstring: *"The PDF is parsed synchronously first …
it is the only way a malformed document can be reported as a 4xx."*

The same root cause makes both CLIs print a raw traceback:
```
cc-parse-syllabus corrupt.pdf   -> rc=1, Traceback (most recent call last): ...
cc-parse-transcript empty.pdf   -> rc=1, Traceback (most recent call last): ...
```
(They handle `FileNotFoundError` and `ValueError` gracefully, with a clean `❌ Error:` line.)

**Suggested fix:** catch `(ValueError, pdfplumber.utils.exceptions.PdfminerException)` —
or simply `Exception` around the `pdfplumber.open` call — in both API helpers and both
CLI mains.

---

### CC-04 — The LLM stage accepts confidently wrong matches at 0.95
**Severity: HIGH** · Module: `skills/matcher.py` + `skills/llm.py` · **Reproduced: yes, live and in stored artefacts**

Three confirmed cases, all `review_status: accepted`, all with fluent justifications.

**(a) Live, via `/api/v1/skills/match`:**
```bash
curl -X POST .../api/v1/skills/match -d '{"terms":[
  {"term":"automation","evidence":"Week 9: build automation and continuous integration"}]}'
```
→ `automation` → **`building automation`**, accepted, 0.950, method `llm`.
The taxonomy's own description of that id: *"Type of automatic control system where
through a Building Managements System or Building Automation System…"* — i.e. HVAC and
smart buildings. The evidence said *build* automation. Confidently, fluently wrong.

**(b) and (c) — already stored in the artefacts the API serves:**
```bash
.venv/bin/python -c "
import json
d=json.load(open('data/extracted/skills/A0413301.json'))   # Operating Systems
for s in d['skills']:
    m=s.get('match') or {}
    if s['term'] in ('communication','Monitors'):
        print(s['term'],'->',m['canonical_label'],m['review_status'],m['match_score'],m['match_method'])
        print('   evidence:',[e['text'][:100] for e in s.get('evidence') or []][:1])"
```
```
communication -> communication skills  accepted 1.0  llm
   evidence: ['Discuss issues of Process Management including process structure,
               synchronization, scheduling, deadlock and communication']
Monitors -> monitoring and observability accepted 0.95 llm
   evidence: ['Monitors']
```
`communication` here is **inter-process communication**. `Monitors` is the **Hoare
concurrency primitive**. They were mapped to an interpersonal soft skill and to DevOps
observability. The same `communication` error occurs in `A0413404` (Internet of Things,
evidence: *"IoT protocols for communication"*) at 0.95.

A fourth, weaker case: `Performance` — the bare section heading, evidence literally the
single word `"Performance"` — → `performance testing`, accepted at 0.648 by the reranker
(over the 0.62 lexical accept threshold).

**End-to-end consequence, reproduced.** A student who passed *only* Operating Systems and
Internet of Things, both grade A:
```
communication skills          class=strong  current=1.0  importance=0.2989  (Backend Development)
monitoring and observability  class=strong  current=1.0  from ['A0413301']
performance testing           class=strong  current=1.0  from ['A0413301']
```
`communication skills` is a top-3 requirement in nearly all nine paths (§13). Two systems
courses now certify it.

**Root cause:** the constrained-LLM stage is asked *"which of these candidates is it?"*
and the shortlist always contains something lexically adjacent. `qwen3:8b` picks the
nearest surface form and reports high confidence; `LLM_ACCEPT_CONFIDENCE = 0.70` lets a
0.95 through unconditionally. Nothing checks whether the *evidence domain* matches the
candidate's description — the taxonomy carries a `description` for exactly these cases and
the accept path never consults it.

**Suggested fix, cheapest first:**
1. Require the LLM to also return a "does the evidence domain match this skill's
   description?" boolean, and route a mismatch to review.
2. Do not let an LLM pick auto-accept a `soft` skill from a technical syllabus —
   `skill_type` is already on the taxonomy record.
3. Raise `LLM_ACCEPT_CONFIDENCE` and add a margin requirement, or cap LLM-accepted
   matches at `needs_review` for single-word generic terms.

---

### CC-05 — M3 classification ignores `coverage`, contradicting §7
**Severity: HIGH** · Module: `skills/gap.py` · **Reproduced: yes**

`ENGINEERING_NOTES` §7 states the two numbers exist because *"proficiency answers how well
did they do; coverage answers how much did they study it. **M3 needs both.**"*

```bash
grep -n "coverage" src/careercompass/skills/gap.py
```
Every hit is the **ontology's** coverage (`req.get("coverage")` → `importance`,
`priority`). The **vector's** `coverage` is never read. `_classify(current, required)`
takes proficiency only.

**Consequence:** one passing mention of a skill in one course, graded A, yields
`proficiency = 1.0` → `classification: strong` → `requirements_met += 1`. It is
indistinguishable from three advanced courses built on the subject. Confirmed above:
`Monitors` appearing once, weight 0.6, level `beginner`, produced
`monitoring and observability: strong, current 1.0`.

Because `proficiency` for a single course is *just the grade*, **every** skill a
single-course student touches comes back at exactly their grade fraction. In the two-course
run above, all 12 "strong" rows read `current_level = 1.0`.

**Suggested fix:** gate `strong` on coverage as well — e.g. require
`coverage >= LEVEL_COVERAGE[required_level]` before a requirement may be classified
`strong`, and demote to `moderate` otherwise. The data is already in the vector; only the
comparison is missing.

---

### CC-06 — `quiz_scores` accepts any float and silently clamps
**Severity: MEDIUM** · Endpoint: `POST /api/v1/skill-vector` · **Reproduced: yes**

```bash
curl -X POST .../api/v1/skill-vector -d '{
  "courses":[{"course_code":"0432405","grade":"D-","status":"passed"}],
  "quiz_scores":{"custom:motion-planning":85}}'
```
**Actual:** HTTP 200.
```json
{"skill_id":"custom:motion-planning","proficiency":1.0,
 "quiz_score":1.0,"proficiency_from_grades":0.1}
```
A caller who sends a percentage instead of a fraction — the single most likely integration
mistake — turns a **D-minus student into a perfect one**, silently, with no warning field.
`SkillVectorRequest.quiz_scores: dict[str, float]` carries no `ge`/`le`.

Related, same call site: an arbitrary key is accepted and injected into the vector —
```json
{"skill_id":"totally:made-up-skill","label":"totally:made-up-skill","proficiency":1.0}
```
No taxonomy validation, and `label` falls back to the raw id.

**Suggested fix:** constrain the value to `0.0–1.0` in the schema so an out-of-range score
is a 422, and reject (or warn on) skill ids not present in the taxonomy.

---

### CC-07 — Invalid `skill_id` in a review decision reports a database outage
**Severity: MEDIUM** · Endpoint: `POST /api/v1/review-queue/decisions` · **Reproduced: yes**

```bash
curl -X POST .../api/v1/review-queue/decisions \
  -d '{"decisions":[{"term":"probe","decision":"corrected","skill_id":"not:a:skill"}]}'
```
**Actual:** `503`
```json
{"type":"database-unavailable","title":"Database is unreachable","status":503,
 "detail":"insert or update on table \"skill_match_reviews\" violates foreign key constraint \"fk_review_skill\""}
```
The database is perfectly reachable. Three problems in one response:
1. A **client error is reported as a dependency outage** — with `Retry-After: 30`, so a
   well-behaved client will retry forever.
2. The **constraint name leaks** to the caller.
3. It is **not atomic**: `record_review` opens its own connection and commits per
   decision, so in a mixed batch the earlier decisions are already committed when the
   request reports 503. I confirmed a valid 3-decision batch commits fine
   (`{"recorded":3,"errors":[]}`), and that a bad id aborts the loop.

**Suggested fix:** catch `psycopg2.errors.ForeignKeyViolation` inside the per-decision
`except` alongside `ValueError` and add it to the existing `errors[]` array (which already
exists for exactly this), reserving 503 for real connection failures.

---

### CC-08 — Legacy `/api/transcript/upload` has four defects
**Severity: MEDIUM** · Module: `api/app.py` · **Reproduced: yes (all four)**

```bash
curl -X POST .../api/transcript/upload -F "file=@data/syllabi/software_design.pdf"
```
**(a) Claims success on a document that is not a transcript:**
```json
{"success":true,"message":"Academic plan parsed successfully.","filename":"software_design.pdf",
 "data":{"student":{"student_name":"","student_id":"",...},"all_courses":[]}}
```
The v1 endpoint correctly returns 422 *"does not look like an MEU academic plan"*. The
legacy one has no such guard.

**(b) Persists without being asked.** `save_output: bool = True`. The upload wrote
`data/extracted/software_design.json` with no flag set. For a real plan this writes a
student's **name, ID, GPA and full grade history** to disk on every request. The v1
endpoint deliberately defaults `save=False` and documents why.

**(c) No size limit.** `shutil.copyfileobj(file.file, buffer)` streams straight to disk;
`_read_pdf`'s 20 MB cap is not applied. A 25 MB upload was accepted (it only failed later,
at parse).

**(d) Wrong error dialect and a 500 where a 4xx belongs:**
```
corrupt.pdf -> 500 {"detail":"Failed to parse PDF academic plan: Unexpected EOF"}  ct=application/json
notpdf.txt  -> 400 {"detail":"Invalid file format. Only PDF files (.pdf) are supported."}
```
Raw exception text, `HTTPException` shape, `application/json` — exactly the "two error
dialects" that `errors.py` says it exists to prevent.

**Suggested fix:** route it through `_read_pdf` + `_parse_transcript_bytes` + `Problem`,
flip `save_output` to default `False`, and add the same "does this look like a plan" guard.
Or delete it — it is documented as kept "so the existing frontend keeps working", and the
brief states there is no frontend.

---

### CC-09 — `build_syllabus_list --help` overwrites a tracked file
**Severity: MEDIUM** · Module: `cli/build_syllabus_list.py` · **Reproduced: yes**

```bash
python -m careercompass.cli.build_syllabus_list --help
```
**Expected:** usage text.
**Actual:** it ignored the flag entirely and regenerated `data/plans/required_syllabi.md`
(a **tracked** file), printing:
```
wrote /home/.../data/plans/required_syllabi.md (690 lines)
total=114 needed=96 have=18 none=0 labs=16
collisions=24 equivalences=2
```
`git diff --stat` afterwards: `data/plans/required_syllabi.md | 12 ++++---`. I restored it
with `git checkout --`.

**Root cause:** the module has no `argparse` and no `def main()` / `if __name__` guard — it
executes `OUT.write_text(...)` at import time. It is the only one of the ten CLIs like
this; it is also not registered as a console script.

**Suggested fix:** wrap it in a `main()` with argparse and a `--check` mode that reports
drift without writing.

---

### CC-10 — `cc-parse-transcript` always writes PII, and exits 0 on a non-transcript
**Severity: MEDIUM** · Module: `cli/parse_transcript.py` · **Reproduced: yes**

**(a) No way to not save.** `--output` overrides the *path*; there is no `--no-save`.
Every run writes `data/extracted/<stem>.json` containing the student's name, ID, GPA and
full grade history. The v1 API endpoint defaults to **not** saving, and documents the
privacy reason. The CLI has no equivalent.

**(b) Silent success on the wrong document:**
```bash
cc-parse-transcript data/syllabi/software_design.pdf ; echo "rc=$?"
```
```
Student Information
   Name:
   ID:
   GPA:       None
Extraction Summary
   Total courses:       0
   Computed GPA:        0.0
rc=0
```
Exit **0**, with a plausible-looking report and a fabricated-looking `Computed GPA: 0.0`.
A valid PDF with no text layer behaves identically. A batch script cannot tell this from
success. This is a fresh instance of the failure class `ENGINEERING_NOTES` §4 is written
about — §4 names three; this is a fourth.

**Suggested fix:** add `--save/--no-save` (default off), and apply the API's guard —
if there is neither a student id nor any course, exit non-zero with a clear message.

---

### CC-11 — CORS echoes any Origin with credentials enabled
**Severity: MEDIUM** · Module: `api/app.py` · **Reproduced: yes**

```bash
curl -i .../api/v1/health/live -H "Origin: https://evil.example"
```
```
access-control-allow-origin: https://evil.example
access-control-allow-credentials: true
```
`allow_origins=["*"]` combined with `allow_credentials=True` makes Starlette reflect the
caller's Origin rather than sending `*`. Any web page a developer visits can call this
service — including `http://127.0.0.1:8000` — and **read the responses**, which include
parsed transcripts. There is no authentication to steal, but there is data to exfiltrate.

**Suggested fix:** set `allow_origins` to the Java service's origin(s) and drop
`allow_credentials` (the service has no cookies or auth headers to carry).

---

### CC-12 — `skills_without_courses` returns unusable identifiers
**Severity: MEDIUM** · Endpoint: `POST /api/v1/recommendations` · **Reproduced: yes**

```json
"skills_without_courses": [
  "custom:robotics-system-architecture",
  "esco:1d86f05e-e9cc-40ce-99d8-2b21cc71b16b",
  "esco:2450c3b3-e78e-435b-b84d-e05d984e71dc",
  "esco:42cb7669-c371-4903-9c0b-13db67b2e4bb", ...]
```
The field is documented as *"the honest answer to 'why is there nothing here for X'"*.
As shipped it is a list of opaque UUIDs. Every `items[]` entry carries `skill_label`; this
list carries none, so nobody can read it without a second lookup against a taxonomy the
calling service does not have.

**Suggested fix:** emit `[{skill_id, skill_label}]`, matching the shape used everywhere
else in the same response.

---

### CC-13 — Generated quizzes ask one fact several times
**Severity: MEDIUM** · Module: `skills/quiz.py` · **Reproduced: yes, on 2 of 4 quizzes**

I generated four quizzes on the live model and graded all 19 keys by hand.

**Docker, 5 questions.** q1–q4 have a **100% identical option set**
(`docker run` / `docker build` / `docker push` / `docker pull`) with the key rotating.
**SQL, 5 questions.** q1–q4 identical option set (`SELECT`/`INSERT`/`UPDATE`/`DELETE`),
key rotating through positions 0, 1, 2, 3 in order.

Measured cross-question overlap:
```
Docker  q1~q2 dice=0.68 identical-option-set=100%     q3~q4 dice=0.86 100%
SQL     q1~q2 dice=0.63 100%                          q2~q4 dice=0.77 100%
```
`validate_question` dedupes on normalised **question text** only; `_similar_options`
compares options **within** one question against `DISTRACTOR_SIMILARITY = 0.80`. There is
**no cross-question check at all**. The self-consistency pass does not help — the model
answers its own trivial recall questions correctly, so all four survive.

A 5-question Docker quiz measures roughly **two** facts. That score then *replaces*
grade-derived proficiency via `apply_quiz_results`. `ENGINEERING_NOTES` §14 documents
"two questions can test one fact" at a 0.73/0.80 near-miss; this is four questions on one
fact at a 100% option-set match, which no threshold currently looks at.

Separately, the prompt's rules are being ignored: it asks for questions that "test whether
someone can use the skill, not whether they memorised a definition" — all 10 Docker/SQL
questions are pure recall — and forbids implausible distractors, yet the cryptography quiz
offered *"Post it on a public forum"* and *"Share it in plain text"* as two of four options.

**Suggested fix:** reject a candidate whose normalised option **set** already appears in an
accepted question, and reject on cross-question text Dice above ~0.60. Both are cheap and
reuse `_normalise` / `_dice`, already imported.

**Answer-key grading (mine, by hand) — see [Human Feedback](#the-student).** 17 of 19 keys
correct; 1 questionable (`gpg --symmetric` keyed as "encrypt using AES-256" — no option
actually specifies AES-256), 1 ambiguous (`git reset --hard HEAD~1` vs `git revert`, both
of which "undo a commit").

---

### CC-14 — `/skills/match` applies no noise filtering, and §5's own examples are unfiltered
**Severity: MEDIUM** · Module: `skills/phrases.py`, `api/app.py` · **Reproduced: yes**

`ENGINEERING_NOTES` §5 opens: *"`development`, `automation`, `activities` are frequent,
grammatically noun phrases, and retrieve something from any taxonomy"*, then presents three
noise sets as the mitigation. None of those three words is in either set:

```bash
.venv/bin/python -c "
from careercompass.skills.phrases import NOISE_TERMS, SYLLABUS_NOISE_TERMS
for t in ['development','automation','activities','presentation']:
    print(t, t in NOISE_TERMS, t in SYLLABUS_NOISE_TERMS)"
```
```
development  False False
automation   False False
activities   False False
presentation False True
```
And the filter only runs inside `extract_skills`. `POST /api/v1/skills/match` calls
`matcher.match()` directly, so nothing is filtered there at all. Live results:
```
development  -> software engineering  accepted 0.950 llm
automation   -> building automation   accepted 0.950 llm
presentation -> communication skills  accepted 0.633 embedding_reranker
```
`presentation` **is** in `SYLLABUS_NOISE_TERMS`, and still sails through this endpoint and
is accepted — a syllabus with a "final presentation" week earns `communication skills`.

One improvement worth recording: `activities` now returns `needs_review` /
low-confidence-no_match rather than §5's documented `sommelier activities`. That specific
case is better.

**Suggested fix:** add the three named words to `NOISE_TERMS`, and apply the noise filter
inside `SkillMatcher.match` (or at the `/skills/match` route) so the guarantee does not
depend on which entry point the caller used.

---

### CC-15 — `no-skill-profile` names the wrong reason and hides the real one
**Severity: MEDIUM** · Endpoint: `POST /api/v1/skill-vector` (and gap/recommendations) · **Reproduced: yes**

```bash
curl -X POST .../api/v1/skill-vector \
  -d '{"courses":[{"course_code":"0432405","grade":"F","status":"passed"}]}'
```
```json
{"type":"no-skill-profile","status":422,
 "detail":"None of the submitted courses have an extracted skill map. 1 of 1 were skipped."}
```
Course `0432405` **does** have a skill map (84 skills). It was skipped because the grade
was an F. The message states the opposite. Identical output for an unrecognised grade
string such as `"P"` (pass/fail), which `GRADE_POINTS` does not know.

`build_skill_vector` records the true reason in `courses_skipped`
(`{"reason": "not passed"}` vs `{"reason": "no skill map"}`), and the error handler
discards it.

**Suggested fix:** include `courses_skipped` in the Problem's `extra` (the mechanism
already exists — `warnings` uses it), and derive the sentence from the actual reasons.

---

### CC-16 — Gap and recommendation responses drop the coverage caveat
**Severity: MEDIUM** · Module: `api/schemas.py` · **Reproduced: yes**

The vector response carries the caveat; the gap response does not.
```
vector keys: [taxonomy_version, source, total_skills, courses_counted, courses_skipped, skills]
gap    keys: [career_path, taxonomy_version, source, summary, total_requirements,
              requirements_met, skills, narrative]
```
For the real 74-course transcript: `courses_counted: 5`, `courses_skipped: 69`
(39 not passed, **30 with no skill map**). The gap built from it reports
`{'strong': 2, 'moderate': 11, 'weak': 74}` with **no indication that 30 of the student's
courses were invisible to the analysis**. `Python: weak, current 0.000` is presented with
the same confidence as every other row.

This is the documented 20-of-114-syllabi coverage gap (PROJECT_STATUS) leaking into output
as apparent fact. The limitation is known; **the response silently omitting it is not**.

**Suggested fix:** carry `courses_counted` / `courses_skipped` through
`SkillGapResponse` and `RecommendationResponse`. It costs two fields and it is the
difference between "you don't know Python" and "we couldn't see 30 of your courses".

---

### CC-17 — gitignore protection depends on the uploader's filename
**Severity: MEDIUM** · Module: `.gitignore`, `api/app.py`, `cli/parse_transcript.py` · **Reproduced: yes**

Both the API (`save=true`) and the CLI write to `EXTRACTED_DIR / f"{Path(filename).stem}.json"`
— a name the **client chooses**. The protecting rule is `*_plan_*.json`.

```bash
for p in data/extracted/my_academic_record.json data/extracted/202411766.json \
         data/extracted/software_design.json data/extracted/CS_AI_plan_x.json; do
  git check-ignore -q "$p" && echo "IGNORED     $p" || echo "NOT IGNORED $p"; done
```
```
NOT IGNORED data/extracted/my_academic_record.json
NOT IGNORED data/extracted/202411766.json
NOT IGNORED data/extracted/software_design.json
IGNORED     data/extracted/CS_AI_plan_x.json
```
`ENGINEERING_NOTES` §9 tells this exact story about the **PDF** rule — *"written for a
filename that no longer existed — none of the five current plan PDFs matched it"* — and
presents it as fixed. The **JSON** rule has the identical defect, and unlike the PDF case
the filename is attacker/uploader-controlled. (`Path(...).stem` does strip directory
components, so there is no traversal here — only the ignore gap.)

**Suggested fix:** ignore `data/extracted/*.json` wholesale (nothing else legitimately
lives at that level — the real artefacts are one directory deeper), or write parsed
transcripts to a dedicated `data/transcripts/` which is already fully ignored.

---

### CC-18 — A failed matcher build is terminal; the instance never recovers
**Severity: MEDIUM** · Module: `api/runtime.py` · **Reproduced: yes (via a real OOM)**

Starting a second instance while the first held the GPU produced:
```json
{"ready": false, "checks": {"taxonomy": {"ok": false, "state": "failed",
  "reason": "OutOfMemoryError: CUDA out of memory. Tried to allocate 978.00 MiB..."}}}
```
The readiness contract behaved **correctly** — this part is a pass. But `warm()` returns
early only for `READY` and `WARMING`; from `FAILED` nothing ever calls it again.
`require()` then raises 503 for the process lifetime. A transient resource failure —
exactly the CUDA OOM that §8 says is expected on this hardware — permanently bricks the
instance until someone restarts it.

**Suggested fix:** allow `require()` (or a background retry with backoff) to re-attempt a
warm from `FAILED`. Also see CC-25: `health()` labels the LLM `failed` in this state
although the LLM is fine — only the matcher build failed.

---

### CC-19 — Server-side temp filename leaked in error details
**Severity: LOW** · Endpoint: `/api/v1/syllabi/preview`, `/api/v1/extractions` · **Reproduced: yes**

```json
{"type":"unparseable-syllabus","status":422,
 "detail":"No text layer found in upload_79d937610f494082b41f30b54c6a2dee.pdf;
           the file is likely a scan and needs OCR before it can be parsed."}
```
The caller uploaded `notext.pdf`. `_parse_pdf_bytes` sets `syllabus["source_file"] = filename`
only on the **success** path; the `ValueError` message is raised from inside the parser,
which only knows the temp path. The client is shown an internal filename instead of their
own — unhelpful, and it exposes the temp-naming scheme.

**Suggested fix:** substitute the user's filename into the message when re-raising as
`Problem.unparseable_syllabus`.

---

### CC-20 — `build_index` shadows its own `skill_ids` parameter
**Severity: LOW** · Module: `skills/course_index.py` · **Confirmed by reading; no current impact**

```python
def build_index(courses, taxonomy, *, min_skills=1, skill_ids=None):
    surface_map = build_surface_map(taxonomy.skills, skill_ids)     # uses the parameter
    for course in courses:
        ...
        skill_ids = in_title | in_body                              # rebinds it
```
Harmless today because the parameter is consumed before the loop. It is a live trap for
the next change — any future use of `skill_ids` after the loop silently reads the last
course's tags.

**Suggested fix:** rename the loop variable to `course_skill_ids`.

---

### CC-21 — Routing-level 404s bypass the Problem contract
**Severity: LOW** · **Reproduced: yes**

```bash
curl ".../api/v1/courses/..%2F..%2Fetc%2Fpasswd/skills"
# -> 404  ct=application/json  {"detail":"Not Found"}
```
Path-traversal attempts are correctly refused (this is a **pass** for T-23), but the
response is Starlette's default shape, not `application/problem+json`. So a client does,
after all, need two parsers — the thing `errors.py` explicitly set out to avoid.

**Suggested fix:** register a `StarletteHTTPException` handler that renders through
`Problem`.

---

### CC-22 — `/health/ready` publishes the database host and port when it is down
**Severity: LOW** · **Reproduced: yes**

```json
{"database": {"ok": false,
  "reason": "connection to server at \"127.0.0.1\", port 59999 failed: Connection refused"}}
```
Unauthenticated endpoint, internal infrastructure detail. No credential leaks — I verified
the DB password appears **0 times** across `/health/ready`, `/api/v1/courses`,
`/openapi.json` and every server log. Combined with CC-11 (any-origin CORS) this is
readable from a browser.

**Suggested fix:** return a fixed `"reason": "connection failed"` and log the detail.

---

### CC-23 — Multi-megabyte JSON re-parsed on every request
**Severity: LOW (functionally) / MEDIUM under load** · **Measured**

Nothing is cached between requests:

| Re-read per request | Size | Cost |
|---|---:|---:|
| `data/extracted/catalog/course_skills.json` — every `/recommendations` | **14.2 MB** | **83.5 ms**, 71 MB peak alloc |
| `data/extracted/skills/*.json` — every vector / gap / recommendation | 1.7 MB | 8.0 ms |
| `career_path_skills.json` — every gap | 0.33 MB | 1.0 ms |
| `taxonomy.jsonl` scan — every gap (`attach_skill_types`) | 0.55 MB | 3.8 ms |
| `taxonomy.jsonl` linear scan — every `/quizzes` (`_taxonomy_skill`) | 0.55 MB | 3.7 ms |

The quiz scan is the most avoidable: `runtime.require().taxonomy.index.get(skill_id)`
already holds the whole taxonomy in memory.

**Effect under concurrency:** serial p50 is 15–103 ms, but at 30 concurrent requests p50
became **3.5 s** across all three endpoints — a ~35–230× degradation from GIL contention
on JSON parsing, plus ~2 GB of transient allocation in flight.

**Suggested fix:** load the catalog index and the course→skill map once, cache by file
mtime, and resolve `_taxonomy_skill` from the already-loaded taxonomy.

---

### CC-24 — Unknown `skill_id` filter returns an empty success
**Severity: LOW** · **Reproduced: yes**
```bash
curl -X POST .../api/v1/recommendations -d '{..., "skill_id":"nope:nope"}'
# -> 200 {"career_path":"Backend Development","total":0,"items":[],"skills_without_courses":[]}
```
A typo is indistinguishable from "no recommendations needed". **Suggested fix:** 404
`skill-not-found` for an id absent from the taxonomy.

---

### CC-25 — `health()` reports the LLM as failed when only the matcher failed
**Severity: LOW** · Module: `api/runtime.py`

In any non-`READY` state, `health()` copies one `unavailable` dict into `taxonomy`,
`vector_index` **and** `llm`. During the CUDA OOM the LLM was reachable throughout;
`/health/ready` reported `llm: {ok: false, state: failed, reason: "OutOfMemoryError..."}`.
Misleading during exactly the incident you would be reading it in.

---

### CC-26 — Four documentation inaccuracies
**Severity: LOW** · **All verified**

| Claim | Where | Reality |
|---|---|---|
| "771 requirements, **82–105** per path" | PROJECT_STATUS | **UI/UX Design has 43**. Range is 43–105 |
| "Course → skill map … **20 of 114** courses" | PROJECT_STATUS | `build_syllabus_list` reports `have=18`, plus 2 orphan fixtures (`0453403`, `A0423501`). ENGINEERING_NOTES §6 correctly says 18 |
| "**Five** of his six endpoints do not exist … **four** working ones he does not know about" | PROJECT_STATUS / §13 | **All six** are absent at their stated paths; **12** implemented endpoints are outside the contract |
| `cc-extract-skills "tests/fixtures/robotics_programming.pdf"` | README | `tests/fixtures/` **does not exist**. ENGINEERING_NOTES §12 says so; README was never updated |

**Contract verification in full** (this is the item PROJECT_STATUS asks to check):

| Contract endpoint | Exists at that path? | Nearest implemented |
|---|---|---|
| `POST /transcript-extract` | NO | `POST /api/v1/transcripts/parse` |
| `POST /skill-vector` | NO | `POST /api/v1/skill-vector` |
| `POST /skill-gap` | NO | `POST /api/v1/skill-gap` |
| `POST /course-recommendations` | NO | `POST /api/v1/recommendations` |
| `POST /quiz-generate` | NO | `POST /api/v1/quizzes` |
| `POST /job-match` | NO | **not implemented** (M6 not started) |

Five are reachable under a different path/name; one does not exist in any form. The
contract also states *"Java will time out and treat the call as failed after the configured
timeout (default 30s)"* — which the async `202` design correctly sidesteps: I measured a
21-term extraction at **47.7 s**, already past that limit, and §8 measures ~104 s/course.

---

### CC-27 — Transferred credit is dropped, not "coverage without attainment"
**Severity: MEDIUM** · Module: `skills/vector.py` · **Reproduced: yes**

The comment above `NON_GRADE_STATUSES` says a transfer credit *"counts toward the plan but
carries no mark, so it contributes coverage without attainment."* The code does not do
that.

`transferred` is not in `NON_GRADE_STATUSES`, but transferred rows carry `grade: None`, so
`_passed()` returns False and the course is dropped entirely with reason `"not passed"`.
On the real transcript that is **20 of 74 courses**.

Worse, the escape hatch makes it wrong in the other direction:
```bash
curl -X POST .../api/v1/skill-vector -d '{"courses":[{"course_code":"0432405",
  "grade":null,"status":"transferred"}],"include_unpassed":true}'
```
```
motion planning  proficiency=0.0  coverage=1.0
sensors          proficiency=0.0  coverage=1.0
```
With `include_unpassed=true`, `_attainment()` returns **0.0** for a missing grade — a
transferred course is scored identically to a failed one, and averaged into the mean. In a
mixed run (one A-graded course plus one transferred), **11 of 46** skills came back at
proficiency 0.0.

**Suggested fix:** make the code match the comment — count transferred courses toward
`coverage` while excluding them from the `weighted_attainment` numerator *and* its
denominator, rather than contributing a zero.

---

## Known / Already Documented Limitations

Hit during testing, already recorded. **Not counted as bugs.**

| Observed | Documented at |
|---|---|
| Only 5 of 74 real transcript courses joined to a skill map (30 skipped for "no skill map") | PROJECT_STATUS *Knowledge base* — 20 of 114 courses; *The critical path* |
| Migrations 004 and 005 unapplied — verified: no `career_path_skills.skill_type`, 0 of 2 catalog tables | PROJECT_STATUS *What is not verified* |
| `bge-m3` and `qwen3:8b` do not fit together on the 8 GB card — reproduced exactly, second instance OOM'd | ENGINEERING_NOTES **§8** |
| CPU embedder faster than GPU — measured 9.56 s vs 13.33 s warm-up | ENGINEERING_NOTES **§6**, **§8** |
| Quiz keys only structurally checked; a key can be confidently wrong | ENGINEERING_NOTES **§14** (I found one questionable and one ambiguous key — see CC-13) |
| Two-letter names (`Go`, `R`, `C`) unreachable, `MIN_TERM_LENGTH = 3` | ENGINEERING_NOTES **§13** |
| Low match rates on theory courses (`0453403` yielded 8 skills; `0412201` only 3 accepted of 50) | ENGINEERING_NOTES **§6** — "a low match rate on a theory course is the taxonomy being honest" |
| YouTube skipped with a warning and no key | PROJECT_STATUS; `catalog/youtube.py` docstring |
| No mentor data; M6 not started | PROJECT_STATUS |
| `CC_RERANKER=auto` can silently fall back and move the accept threshold 0.72→0.62 | ENGINEERING_NOTES **§4** |
| Job history is in-memory and lost on restart | `api/jobs.py` docstring; surfaced in the 404 detail |

**One near-miss worth separating.** The `"generative AI"` alias on
`custom:large-language-models` caused *"Adobe Photoshop for Beginners: Generative AI
Images"* and *"Introduction to Generative AI in Legal"* to be recommended for an LLM gap.
That is the §5/§12e over-broad-alias **family**, but this specific alias is new, is
hand-written in `custom_skills.json` (not inherited from ESCO), and is not covered by
`_is_head_noun_alias` (it is two words). Reported as new — see [Biggest Problems](#biggest-problems).

---

## Failed Tests

No test in `tests/` failed. **All ten suites pass: 719 checks, 0 failures**, both before and
after my work.

| Suite | Checks | Result | vs. §12 table |
|---|---:|---|---|
| `test_syllabus_parser` | 65 | ✅ | matches |
| `test_skill_extractor` | 82 | ✅ | matches |
| `test_skill_matcher` | 232 | ✅ | matches |
| `test_job_extractor` | 56 | ✅ | matches |
| `test_job_corpus` | 41 | ✅ | matches |
| `test_transcript_parser` | 37 | ✅ | matches |
| `test_skill_vector` | 39 | ✅ | matches |
| `test_skill_gap` | 49 | ✅ | matches |
| `test_skill_quiz` | 74 | ✅ | matches |
| `test_course_recommend` | **44** | ✅ | docs say 38 — the uncommitted `course_index` fix adds 6 |

**The 26 failures in this report are all hand-written tests of behaviour the suites do not
cover.** That gap is the finding: 719 green checks coexist with a process-killing upload,
a student credited with a skill they never studied, and a student denied one they did.
Specifically, no suite covers any HTTP endpoint, any malformed PDF, or any cross-module
join between the artefacts and the live taxonomy.

---

## Not Tested / Blocked

| Area | Why |
|---|---|
| **Anthropic provider** | `anthropic` not installed (`llm` extra absent) and `ANTHROPIC_API_KEY` spends real money. **Code review only** — the provider is selected by `CC_MATCH_LLM_PROVIDER` and shares `LLMDecider`'s interface; nothing suspicious read, but nothing executed |
| **YouTube ingestion** | No `CC_YOUTUBE_API_KEY`. Verified only that the no-key path returns `[]` with a warning and does not fail the run |
| **LinkedIn scraping** | Forbidden by the brief. `jobs/` exercised only against the existing `data/raw/` + `data/clean/` corpus |
| **Coursera / MIT Learn ingestion** | Live catalog pulls not run. The *derived index* was tested thoroughly, and 10 of its URLs fetched |
| **Migrations 004 and 005 execution** | Would alter the schema of a live database I did not own. Verified their **absence** read-only |
| **True cold BGE index build (~237 s)** | `vector_index.npz` is prebuilt and the brief forbids regenerating `data/` artefacts. **Every warm-up I measured (9.5–13.5 s) is a cached-index load, not a cold build.** The 237 s figure is unverified here |
| **Cross-encoder reranker** | `CC_RERANKER=lexical`; switching to `cross` triggers a 2.1 GB model download. **All matcher thresholds in this report are the lexical set** (0.62 / 0.40) |
| **`grade_quiz()`** | Not exposed by any endpoint — by design (`app.py` says the calling service grades). 74 suite checks cover it; I could not exercise it over HTTP |
| **M6 job/mentor matching** | Not started upstream. No mentor data of any kind exists |
| **`missing-course-code` over HTTP** | I could not craft a PDF with an extractable text layer but no course code. Verified the branch at unit level: `Problem.missing_course_code()` → 422, type `missing-course-code`, warnings carried |
| **Sustained load / soak** | Single 30-way burst only. No multi-hour run, no memory-leak observation |

---

## Data & Artefact Integrity

**Clean:**

| Check | Result |
|---|---|
| Taxonomy size / version | 903 skills, v1.0 — matches docs |
| Duplicate skill ids | **0** |
| Duplicate normalised labels | **0** |
| Qualifier-stripped label collisions (the §2 `Java` defect shape) | **0** — the `merge_skills` fix holds |
| Ontology rows | 771; **0** orphan `skill_id` |
| Ontology `coverage` outside 0–1 | **0** |
| Ontology rows at coverage > 0.99 (the §2 summed-posting-ids smell) | **0** — the union fix holds |
| Catalog index orphan skill keys | **0** |
| Catalog skills not required by any career path | **0** — the ontology restriction is enforced |
| Sample sizes sum | 2,238 — matches the documented corpus exactly |

**Not clean:**

| Finding | Detail |
|---|---|
| **Retired ids in served artefacts** | `custom:java` ×4, `custom:python` ×1 — **CC-02**. DB is clean; the JSON is not |
| **DB and disk disagree on scope** | `data/extracted/skills/` has **20** courses; `course_skills` has **4** (`0412201`, `0432405`, `0434402`, `0443501`). Any consumer reading the DB sees a fifth of the knowledge base. Benign while every API path reads JSON, but it is an undocumented divergence |
| **Missing course titles** | `0432405.json` has `course_title: null`; `course_codes` is `null` on all 20 artefacts, so `load_course_skills`'s multi-code join (§3, the whole reason the field exists) is inert |
| **2 orphan syllabus fixtures** | `0453403` (ethical hacking), `A0423501` (software architecture and design) extracted but not on any plan — reported by `build_syllabus_list`, consistent with the §3 collision problem |
| **26 career-path skills have no catalog course** | Honest catalog coverage limit; surfaced by `skills_without_courses` (but unreadably — CC-12) |
| **14.2 MB derived artefact tracked in git** | `data/extracted/catalog/course_skills.json`, currently a 377,608-line uncommitted diff |

**Working-tree hygiene.** The uncommitted `course_index.py` change is a **real, verified
improvement** (see What's Working Well). I restored everything my tests touched:
`data/plans/required_syllabi.md` (`git checkout --`), two stray `data/extracted/*.json`
files, 21 `course_skills` rows and 2 `skill_match_reviews` rows. Final `git status` matches
the state at the start of the session — the same three modified files, nothing else.

---

## Model-Dependent Behavior

**What was active for every result in this report:** BGE-M3 retrieval (`st:BAAI/bge-m3`,
903 entries) + **lexical** reranker + `ollama:qwen3:8b` at `temperature=0`, database
present.

| Aspect | Observed |
|---|---|
| **Thresholds in force** | Lexical family: `accept_score=0.62`, `review_floor=0.40`, `accept_margin=0.05`, `LLM_ACCEPT_CONFIDENCE=0.70`. The cross-encoder set (0.72/0.45) was **never exercised** |
| **LLM determinism** | Strong. Re-running a full 21-term extraction reproduced **21 of 21 decisions identically** against the artefact stored days earlier — `temperature: 0` plus structured output does what it promises |
| **LLM contribution** | On a 21-term course: 9 of 21 decisions came from the `llm` method, 12 from `embedding_reranker`. The LLM is deciding roughly **43%** of terms — it is not a rare tiebreak, it is a primary decision-maker. That is why CC-04 matters so much |
| **LLM off** | `use_llm=false` on `/skills/match` answers in **4.4 ms** for 3 terms vs **253 ms** for one ambiguous term with the LLM on — a ~170× difference per ambiguous term. With the LLM off, ambiguous terms fall to `needs_review` instead of being decided; `degraded` correctly stays `false` when the LLM is *configured* off, and would flip `true` only if it were wanted and unreachable (design verified by reading `jobs.py`; not triggered live, since Ollama never went down) |
| **BGE vs lexical** | **Not comparable from this run.** `tests/test_skill_matcher` builds its own **lexical** test index (`retrieval: lexical-ngram-v1 reranker: lexical`) and completes in 2 s. Its 232 checks are therefore **not evidence about the BGE path**, and none of my API results are evidence about the lexical path. Two separate backends, no shared measurement |
| **Embedder placement** | GPU warm 13.33 s / 13.51 s; CPU warm 9.56 s. **CPU was faster**, reproducing §6 and §8. GPU instance: 1,742 MB RSS + 2,324 MiB VRAM. CPU instance: 2,534 MB RSS |
| **Could not compare** | cross-encoder reranker (2.1 GB download), Anthropic provider (not installed, paid), `qwen3:4b` (present, but §8 says it auto-accepts bad matches — deliberately not substituted) |

---

## Security Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| S-1 | **PDF decompression bomb → OOM kill** (CC-01). 354 KB upload, 295:1 ratio, 12.4 GB RSS, both servers killed | **Critical** | Reproduced twice |
| S-2 | **CORS reflects any Origin with `allow_credentials: true`** (CC-11) | Medium | Reproduced |
| S-3 | **Legacy endpoint has no upload size limit** (CC-08c) — `shutil.copyfileobj` straight to disk | Medium | Reproduced with 25 MB |
| S-4 | **PII persisted by default** — legacy endpoint `save_output=True`; `cc-parse-transcript` always writes (CC-08b, CC-10a) | Medium | Reproduced |
| S-5 | **gitignore gap on client-named transcript output** (CC-17) | Medium | Reproduced |
| S-6 | **FK violation leaks a constraint name and reports 503** (CC-07) | Medium | Reproduced |
| S-7 | **`/health/ready` publishes DB host:port on failure** (CC-22) | Low | Reproduced |
| S-8 | **Server temp filename leaked in 422 detail** (CC-19) | Low | Reproduced |
| S-9 | **Routing 404s escape the Problem contract** (CC-21) | Low | Reproduced |

**Verified clean:**

- **SQL injection: none.** Every statement in `db/skills.py` and `db/jobs.py` is
  parameterised (`%s`, `execute_batch`, `ANY(%s)`). The single f-string —
  `f"UPDATE {table} SET skill_id = %s WHERE skill_id = %s"` — interpolates a hard-coded
  `("course_skills", "job_skills")` tuple, never user input.
- **Path traversal: none reachable.** `/courses/{course_code}` is guarded by
  `COURSE_CODE_RE = ^[A-Za-z0-9_-]{1,64}$` before touching the filesystem, and the router
  normalises encoded traversal to a 404. Upload paths use a `uuid4` temp name; output paths
  use `Path(filename).stem`, which strips directory components. `run_migration(filename)`
  joins an unvalidated name onto `MIGRATIONS_DIR`, but all four call sites pass module
  constants — not reachable, worth a docstring note.
- **Secrets: no leak.** The `CC_DB_PASSWORD` value appears **0 times** in
  `/api/v1/health/ready`, `/api/v1/courses`, `/openapi.json`, or any server log across
  every run.
- **Temp file hygiene:** `data/temp/` was empty after every failure path — the `finally:
  unlink()` blocks work, including on the 500 paths.
- **Upload limits on v1:** 20 MB enforced correctly (413 with the documented Problem shape).
- **Batch caps:** `/skills/match` caps at 25 terms with a 413 and a genuinely helpful
  message; `question_count` capped at 10; `limit` capped at 50/200/500 as documented.

---

## Performance Findings

All measured on this machine. **Every warm-up figure is a cached-index load** — see
Not Tested.

**Warm-up (`/health/ready` → 200):**

| Run | Placement | `warm_seconds` |
|---|---|---:|
| 1 | GPU | **13.33 s** |
| 2 | GPU (restart) | **13.51 s** |
| 3 | CPU (`CUDA_VISIBLE_DEVICES=""`) | **9.56 s** |

`/health/live` answered in **1.0–1.7 ms** throughout the build; `/health/ready` returned
503 with `Retry-After: 30`. The separation works exactly as designed.

**Warm serial latency (p50 of 7, single client):**

| Endpoint | p50 | min | max |
|---|---:|---:|---:|
| `GET /health/live` | 4.2 ms | 4.0 | 4.5 |
| `GET /health/ready` (opens a DB connection every call) | 14.0 ms | 10.9 | 16.0 |
| `GET /courses` | 10.6 ms | 10.2 | 11.3 |
| `GET /courses/0432405/skills` | 6.0 ms | 5.9 | 6.2 |
| `POST /skill-vector` (74 rows) | 15.1 ms | 11.2 | 60.8 |
| `POST /skill-gap` | 16.0 ms | 15.8 | 16.5 |
| `POST /recommendations` | **102.9 ms** | 102.1 | 103.7 |
| `GET /review-queue?limit=100` | 16.2 ms | 14.1 | 16.8 |
| `POST /skills/match` (3 terms, LLM off) | 4.4 ms | 4.2 | 4.5 |
| `POST /skills/match` (1 ambiguous term, **LLM on**) | **252.6 ms** | — | — |
| `POST /transcripts/parse` (74-course PDF) | 260 ms | — | — |

**Under concurrency (30 simultaneous):**

| Endpoint | serial p50 | 30-way p50 | factor |
|---|---:|---:|---:|
| `/skill-vector` | 15.1 ms | **3,464 ms** | 229× |
| `/skill-gap` | 16.0 ms | **3,471 ms** | 217× |
| `/recommendations` | 102.9 ms | **3,489 ms** | 34× |

All 30 returned 200 with a **single distinct response body** per endpoint — correctness
held. The collapse is CC-23: every request re-parses 14.2 MB (recommendations) or 1.7 MB
(vector/gap) of JSON, and those parses serialise on the GIL.
`POST /skills/match` × 24 parallel stayed at **81 ms p50** — the matcher path itself is fine.

**Extraction throughput:** a 21-term course took **47.7 s** end to end (~2.3 s/term with
LLM routing), against §8's measured ~104 s/course for larger syllabi. Progress advanced in
chunks of 8 (`MATCH_CHUNK`) and cancellation landed at a chunk boundary as designed.
**This already exceeds the Java contract's 30 s timeout**, confirming the `202`-plus-job
design was necessary.

**Memory:**

| | |
|---|---:|
| GPU instance RSS | 1,742 MB (+ 2,324 MiB VRAM) |
| CPU instance RSS | 2,534 MB |
| Catalog index resident, per `/recommendations` call | 23.6 MB |
| Peak transient allocation, per `/recommendations` call | **71.0 MB** |
| Peak RSS during the PDF bomb | **12,354 MB** → OOM kill |

**No quadratic loops found** over the 2,238-posting corpus. The heaviest inner loop is
`skills_in_text` (O(4·N) normalises per document), which runs at catalog build time, not
per request.

---

## Human Feedback

### The backend developer

I integrated against this for a day. Here is what actually happened.

**The contract was not obvious, and the document I was given was wrong.** I had
`CareerCompass-AI-Service-Contract (2).docx`. I called `POST /skill-vector` and got a 404.
I called all six endpoints from the contract; **all six 404'd**. Every one lives under
`/api/v1/`, and two are renamed outright — `/course-recommendations` is
`/api/v1/recommendations`, `/quiz-generate` is `/api/v1/quizzes`. `/job-match` does not
exist at all, and I only learned that from `PROJECT_STATUS.md`, not from any error. I found
the real routes by fetching `/openapi.json`. That is a working answer, but nobody told me
to do it, and `PROJECT_STATUS.md` says "five of six" when it is six.

**The error responses are genuinely excellent — right up until they aren't.** This 404 is
the best I have seen in a while:

> *"No extraction with id '0413203'. Extraction ids come from the 202 response of POST
> /api/v1/extractions and look like 'ext_d37e7f4edc45'. Job history is held in memory and
> is lost on restart… To read stored results for course 0413203, use GET
> /api/v1/courses/0413203/skills instead."*

It diagnosed my actual mistake and handed me the right call. The `career-path-not-found`
404 lists all nine valid names. The 413 on `/skills/match` tells me to use `/extractions`
for bulk. Somebody thought hard about the person on the other end.

Then I posted a corrupt PDF and got **500 `{"type":"internal-error"}`** with no detail —
which is correct behaviour for a genuine bug, so I spent forty minutes assuming the service
was broken before I found it was *my* file. A malformed upload is the single most common
thing a file API receives; it must be a 422. It is even documented as one: the docstring on
`create_extraction` says parsing happens up front so "a malformed document can be reported
as a 4xx." It isn't.

**I had to read the source three times.**

1. I sent `{"courses":[{"course_code":"0432405","grade":"F"}]}` and got
   *"None of the submitted courses have an extracted skill map."* I spent twenty minutes
   confirming `0432405` **does** have a skill map (84 skills — I checked
   `/api/v1/courses`). Only after reading `vector.py:_passed()` did I understand the real
   reason was the F grade. The response even computes the true reason into
   `courses_skipped` and then throws it away. Same message for grade `"P"` — we have
   pass/fail courses, and I have no idea what the service does with them because it never
   says.
2. `min_weight` — I could not tell from the docs whether it filters the extractor's weight
   or the match score. I read `extractor.py`.
3. `quiz_scores` — nothing says the scale. I guessed percentages, sent `85`, got HTTP 200
   and a student at proficiency `1.0`. **No error, no warning.** I only caught it because
   the number looked too good. If I had shipped that, every quizzed student would have
   scored perfectly and the numbers would have looked plausible for months. Please make
   that a 422.

**What made me hesitate before shipping.**

- **Grading is not here.** `/api/v1/quizzes` returns the `answer_key` and tells me *I*
  grade it. Fine — except `grade_quiz()` exists in `quiz.py` with 74 tests behind it,
  including `_normalise()` semantics for free-text answers (NFKD folding, keeping
  `/ % + - ^ = < >` so `1/2` and `1.2` stay distinct). I now have to reimplement that in
  Java and keep it in sync, or my grading disagrees with your tests. Either expose
  `POST /api/v1/quizzes/grade`, or document the normalisation rules as part of the contract.
- **`skills_without_courses` is unreadable.** I get
  `["esco:1d86f05e-e9cc-40ce-99d8-2b21cc71b16b", ...]`. Every `items[]` entry has a
  `skill_label`; this list has none. I cannot show it to anyone. I need `{skill_id, label}`.
- **The gap response hides its own caveat.** `/skill-vector` tells me `courses_counted: 5,
  courses_skipped: 69`. `/skill-gap`, built from the exact same call, tells me nothing —
  and it is the one I display. I nearly shipped a screen saying "you have no Python" for a
  student whose Python course simply had no syllabus loaded.
- **Job state is in memory.** Documented, and the 404 says so, which I appreciate. But it
  means an instance restart loses every in-flight extraction, and CC-01 means a single bad
  upload *causes* that restart.
- **Two error dialects after all.** `errors.py` opens by explaining that it exists so I
  don't need two parsers. I need two: `application/problem+json` for everything real, and
  `{"detail": ...}` for routing 404s and every legacy-endpoint failure.

**What I'd happily ship against:** the async `202` + `Location` + poll flow. Idempotency by
content hash worked first time and returned in 4 ms. `force=true` did what it says.
Cancellation landed. `/health/live` vs `/health/ready` is correct and saved me from
configuring a liveness probe that would have killed the container during warm-up. The
`career_path` is a name, not an id — thank you, that decision saved us a coupling argument.

---

### The student

I'm in my fourth year of CS/AI. I uploaded my academic plan and asked for the AI &
Machine Learning path.

**The first screen told me I have 2 strengths and 74 weaknesses.** My first reaction was
that it must be broken. My second was that maybe it isn't. Neither is a good reaction to
have.

**Then I saw "Python — no evidence, top priority."** I have written Python for three years.
I passed the course. The system had already put `Python` in my skill vector at proficiency
1.0 — it just filed it under an id the career-path table doesn't recognise, so the gap
counted it as zero. Same for Java: I got an **A** in Object Oriented Programming in Java,
and it tells me Java is a complete gap. If a tool tells me I don't know the two languages I
actually know, I stop believing the other 72 rows. **That one error costs the whole report
its credibility**, and it isn't even a hard question — it's a stale identifier.

**And 30 of my courses were invisible.** Not wrong — invisible. There is no syllabus loaded
for them, so they contributed nothing. The vector knew this. The screen I was shown did not
mention it. "You have no evidence of X" and "we couldn't see 30 of your courses" are
extremely different sentences, and I was shown the first one.

**The one thing it was too confident about, in the other direction:** I ran it on just
Operating Systems and Internet of Things, and it told me I'm **strong at communication
skills**. I know exactly why — my OS syllabus says "process synchronization, deadlock and
communication", meaning inter-process communication, and my IoT syllabus says "IoT
protocols for communication." Neither of those made me better at talking to people. It also
credited me with **monitoring and observability** because my OS course covers *monitors*,
the concurrency primitive. If I put "observability" on my CV because this told me to, and
an interviewer asks me about Prometheus, that is a genuinely bad afternoon. **Being wrongly
told I'm good at something is worse than being wrongly told I'm bad at it**, because I
won't go and check.

It also decided I'm strong at everything I touched *at exactly the same level*. Every
single "strong" row read 1.0. One mention in one course I got an A in scores the same as
three courses built on the subject. The system computes a `coverage` number that would tell
these apart, and then doesn't use it.

**The courses were the best part.** Real links, and I clicked ten of them — all ten
loaded. The explanations are written about *me*, not lifted from marketing copy: *"Your
coursework shows no evidence of PyTorch, and 28% of postings on this path ask for it. This
is a beginner-level course."* The 28% is what makes it land — it's telling me why this is
worth my Saturday. And it sent me the *beginner* PyTorch course, not the advanced one,
because it knows I'm at zero. That's genuinely thoughtful.

Two of them were nonsense, though. To learn **large language models** it recommended
**"Adobe Photoshop for Beginners: Generative AI Images"** and **"Introduction to Generative
AI in Legal"**. Photoshop's generative fill is not an LLM, and I'm not going into law. Both
matched on the words "Generative AI" in the title. When two of my top ten are obviously
silly, I start skimming the rest instead of trusting them.

**Would I accept a grade from the quiz?** No. Not because it's wrong — because it's
lazy.

The Docker quiz asked me five questions. Four of them had **the same four options**:
`docker run`, `docker build`, `docker push`, `docker pull`. Question 1 was "which builds
an image", question 2 "which runs a container", question 3 "which pushes", question 4
"which pulls". That is **one** question. The SQL quiz did exactly the same thing with
`SELECT`/`INSERT`/`UPDATE`/`DELETE`, and the right answer went 0, 1, 2, 3 in order — I
could have passed it by pattern-matching without reading. If I get 5/5 on that, the system
records that I am proficient in Docker and **overwrites the proficiency it inferred from my
actual coursework**. It measured whether I can recall four command names.

The keys were mostly right — I checked all 19 myself. Two I'd argue with:

- **Git:** *"Which command undoes a commit and reverts the working directory to the previous
  state?"* Key: `git reset --hard HEAD~1`. But `git revert` is right there as option 1, and
  it also undoes a commit and leaves my working directory at the previous content. The real
  distinction is rewriting history vs. adding an inverse commit, and the question doesn't
  ask that. I know Git well and I hesitated — which is the exact failure the notes warn
  about, where knowing more makes you *more* likely to get it wrong.
- **Cryptography:** *"Which command encrypts a file using AES-256 in GPG?"* Key:
  `gpg --symmetric --armor file.txt`. That does symmetric encryption, but it doesn't
  specify AES-256 — you need `--cipher-algo AES256` for that. **No option specifies
  AES-256.** The question asks something none of its answers answer.

And in that same crypto quiz, one question offered "Send it via email", "Share it in plain
text" and "Post it on a public forum" as three of four options for secure key exchange.
That isn't a question, it's a formality.

**Where it feels confident about something it shouldn't:** everywhere it prints a number.
`current_level: 0.000` looks measured. It isn't — it can mean "we assessed you and you have
none", or "your course had no syllabus", or "your skill is filed under a retired id". Those
three deserve three different sentences, and I get one number for all of them.

**What I'd want changed before I'd trust it:** tell me which of my courses you couldn't see.
Fix Java and Python. Stop telling me I'm good at communication because my OS course
mentioned IPC. And make the quiz ask five different questions.

---

## What's Working Well

Worth stating clearly, because most of this system is good.

- **Determinism is real, not aspirational.** M2, M3 and M4 all produced **byte-identical**
  responses across repeat runs. The tie-break-by-id sorting in `vector.py`, `gap.py` and
  `recommend.py` was deliberate and it works.
- **The LLM path is more stable than advertised.** A full 21-term extraction reproduced
  **21 of 21 decisions** identically against an artefact generated days earlier.
  `temperature: 0` plus constrained JSON output is doing its job.
- **Thread safety holds under pressure.** 24 parallel `/skills/match` and 30 parallel
  M2/M3/M4 calls: 54/54 succeeded, **one distinct response body per endpoint**. I could
  not corrupt the shared `MatcherRuntime`.
- **The health split is correct and I proved it by accident.** When the second instance
  hit a real CUDA OOM, `/health/live` kept answering and `/health/ready` reported 503 with
  the actual `OutOfMemoryError` text. An orchestrator would have done exactly the right
  thing.
- **The error contract is 58/61 correct**, in genuine `application/problem+json`, with
  `Retry-After` on every 503 and 507. Where it fails it fails at the edges, not the core.
- **Error *messages* are outstanding.** The `extraction-not-found` 404 that detects a
  course code and redirects you; `career-path-not-found` listing all nine names; the 413
  telling you which endpoint to use for bulk. This is rare and it should not be lost.
- **The async job design is validated by measurement.** My 21-term extraction took 47.7 s —
  already past the Java contract's 30 s timeout. The `202` + `Location` + poll + cancel flow
  is not over-engineering; it is the minimum that works.
- **Idempotency by content hash + taxonomy fingerprint** is the right key, and it returned
  a cached result in **4 ms**.
- **The licence boundary is genuinely enforced.** I checked: `build_index` never copies
  `description`, the persisted index carries a `WARNING` field explaining why, and
  `.gitignore` excludes `data/raw/catalog/`. Three independent enforcement points, each
  carrying its reason. This is how you make a policy survive.
- **M4's explanations are written from the student's gap, and it shows.** *"Your coursework
  shows no evidence of PyTorch, and 28% of postings on this path ask for it"* is better
  advice than any course description would give, and it comes with the right difficulty
  level attached.
- **The `_relevance` de-saturation fix worked.** Scores ranged 0.8180–0.8655 across the top
  ten — a real ranking, not everything clipped to 1.000.
- **The §2 identity fixes hold.** Zero duplicate ids, zero duplicate labels, **zero
  qualifier-stripped collisions**, zero ontology rows at coverage > 0.99. The union-of-
  posting-ids fix and the `merge_skills` fold are both still correct.
- **The uncommitted `course_index.py` change is a substantial, verified win.** I stashed it
  and re-measured to be sure: CSS **0 → 277** courses, NoSQL 0 → 78, Ansible 0 → 69,
  Metasploit 0 → 17, Xcode 0 → 24; the index grew 162 → 187 skills. CSS is asked for by 14%
  of Backend postings and previously matched **nothing**. This should be committed.
- **`ENGINEERING_NOTES.md` is the most useful document in the repository.** Several of my
  findings are refinements of things it already predicted. A team that writes down "the
  obvious optimisation was wrong four times out of five" is a team that will fix these.

---

## Biggest Problems

Ranked by impact on someone actually depending on this service.

1. **A 354 KB upload kills the process** (CC-01). Availability, trivially triggerable,
   takes down in-flight jobs and co-resident instances. The 20 MB limit measures the wrong
   number.
2. **Retired skill ids silently erase real skills** (CC-02). An A in Java reads as a total
   gap. It is five rows in five JSON files, it is the exact failure §2 was written about,
   and it destroys the student's trust in every other number on the page.
3. **The LLM accepts confidently wrong matches at 0.95** (CC-04). IPC → communication
   skills; OS monitors → observability; build automation → building automation. It decides
   ~43% of terms, so this is not an edge case, and a wrong canonical id is invisible once
   stored.
4. **M3 ignores coverage** (CC-05). One word in one course, graded A, becomes "requirement
   met". It makes every "strong" claim in the product unreliable, and the fix is a
   comparison the data is already sitting there for.
5. **Malformed PDFs return 500** (CC-03). The most common bad input on a file API, reported
   as a server bug, contradicting the design note in the same file. Also produces raw
   tracebacks from both CLIs.
6. **Output hides its own uncertainty** (CC-16, CC-15, CC-12). The gap drops
   `courses_skipped`; the 422 names the wrong reason; `skills_without_courses` is UUIDs.
   Individually small, collectively they turn "we couldn't see your courses" into "you
   don't have the skill."
7. **`quiz_scores` silently clamps** (CC-06). One plausible integration mistake — sending
   85 instead of 0.85 — marks every student perfect, permanently, with no signal.
8. **Quizzes measure less than they claim** (CC-13). Four of five questions on one fact,
   and the score *overwrites* a real measurement.
9. **PII persisted by default in two places** (CC-08b, CC-10a), landing on paths the
   gitignore rule does not cover (CC-17).
10. **Per-request re-parsing collapses under concurrency** (CC-23). 15 ms → 3.5 s at 30
    concurrent. Fine today, a wall the first time real traffic arrives.

---

## Recommended Fixes

### P0 — Fix immediately

1. **Bound PDF decompression** (CC-01). Cap decompressed text and page count, add a parse
   timeout, ideally parse in a `setrlimit`-capped subprocess. Nothing else on this list
   matters if one upload kills the box.
2. **Remap retired ids in `data/extracted/skills/*.json`** (CC-02), and make
   `load_course_skills` resolve every `canonical_id` through the alias index at load time,
   logging loudly on a miss. Add "run the remap over the JSON artefacts too" to the merge
   procedure in §2.
3. **Catch `PdfminerException`** in `_parse_pdf_bytes`, `_parse_transcript_bytes` and both
   CLI mains (CC-03). Four lines.
4. **Constrain `quiz_scores` to 0.0–1.0** in the schema (CC-06). One line, prevents a
   silent, months-long data corruption.

### P1 — Fix soon

5. **Stop the LLM auto-accepting domain mismatches** (CC-04): require an evidence-domain
   confirmation, refuse to auto-accept a `soft`-typed skill from a technical syllabus, and
   route single-word generic terms to review regardless of reported confidence.
6. **Gate `strong` on coverage as well as proficiency** (CC-05).
7. **Carry `courses_counted` / `courses_skipped` through the gap and recommendation
   responses** (CC-16), and put the real skip reasons into the `no-skill-profile` detail
   (CC-15).
8. **Add the three §5 noise words to `NOISE_TERMS`, and filter inside `SkillMatcher.match`**
   so the guarantee does not depend on the entry point (CC-14).
9. **Reject cross-question duplicate option sets and high text overlap in quizzes** (CC-13).
10. **Fix the review-decision error path** (CC-07): FK violation → per-decision `errors[]`,
    not a 503; make the batch atomic on one connection.
11. **Fix or delete the legacy endpoint** (CC-08) — default `save_output=False`, enforce the
    size limit, use `Problem`, add the "is this a plan" guard.
12. **Add `--save/--no-save` (default off) to `cc-parse-transcript`, and exit non-zero on a
    non-plan** (CC-10).
13. **Lock CORS down** to the Java service's origin and drop `allow_credentials` (CC-11).
14. **Widen the gitignore rule** to `data/extracted/*.json` (CC-17).

### P2 — Improve

15. **Cache the catalog index and course→skill map by mtime; resolve `_taxonomy_skill` from
    the loaded taxonomy** (CC-23).
16. **Give `skills_without_courses` labels** (CC-12).
17. **Allow re-warm from `FAILED`** with backoff (CC-18).
18. **Make transferred credit behave the way its own comment describes** (CC-27), and decide
    explicitly what a `"P"` grade means.
19. **404 on an unknown `skill_id` filter** in `/recommendations` (CC-24).
20. **Register a `StarletteHTTPException` handler** so routing 404s speak `problem+json` (CC-21).
21. **Fix the four documentation inaccuracies** (CC-26) — especially the README's
    `tests/fixtures/` path and PROJECT_STATUS's "five of six", which is now "six of six".
22. **Expose `POST /api/v1/quizzes/grade`**, or publish `_normalise`'s rules in the contract.
23. **Populate `course_codes` in the extracted artefacts** so the §3 multi-code join actually
    functions, and fill the missing `course_title` on `0432405`.

### P3 — Nice to have

24. Rename the shadowed loop variable in `build_index` (CC-20).
25. Report per-dependency state accurately in `health()` when the matcher failed (CC-25).
26. Generalise `reason` in `/health/ready` and log the detail (CC-22).
27. Substitute the user's filename into parse-failure details (CC-19).
28. Add a `"cancelling"` job status so `DELETE` doesn't return `"running"`.
29. Reconcile the DB (4 courses) with disk (20 courses), or document the divergence.
30. Add an HTTP-level smoke suite — every finding in this report came from territory the
    719 existing checks do not enter.

---

## Final Verdict

### Needs fixes before release

Judged as an AI service sitting behind someone else's backend — not as a consumer product.

**The engineering underneath is good.** The determinism claims are true and I verified them
byte-for-byte. The concurrency design is sound and I could not break it. The async job
model is correct, and my own measurement (47.7 s for a small course, against a 30 s client
timeout) proves it was necessary rather than speculative. The error contract is real, the
error *messages* are better than most production APIs I have integrated against, and the
licence boundary is enforced in three independent places with the reasoning written down.
`ENGINEERING_NOTES.md` predicted several of my findings before I made them.

**It cannot ship yet for three specific reasons**, none of which is architectural:

1. **Availability.** A 354 KB PDF terminates the process. Anything can be built on top of a
   service that returns bad answers; nothing can be built on one that dies. This is a
   half-day fix.
2. **Silent data corruption in both directions.** Five stale ids tell a student with an A in
   Java that they have no Java. Three accepted-at-0.95 mismatches tell a student who studied
   inter-process communication that they are strong at interpersonal communication. Both are
   invisible to every existing test, and both are exactly the failure classes the project's
   own notes are written about. §2 warned about the first; the fix was applied to the
   database and not to the files the API actually reads.
3. **The output does not carry its own uncertainty.** The service *computes* that it could
   only see 5 of a student's 74 courses, and then serves a gap analysis that does not
   mention it. That is not a coverage problem — the coverage gap is known, documented and
   legitimate. It is a **presentation-of-confidence** problem, and it is what turns a known
   limitation into a wrong answer a student acts on.

The P0 list is four items and none is deep: bound the decompression, remap five ids, catch
one exception class, add one range constraint. With those done, and CC-04, CC-05 and CC-16
from P1, I would call this **ready with minor fixes** and be comfortable putting a Java
service in front of it.

What I would not do is treat the 719 passing checks as evidence of readiness. They pass,
they are well written, and they test the arithmetic thoroughly — but not one of them makes
an HTTP request, opens a malformed PDF, or joins the stored artefacts against the live
taxonomy. Every serious finding in this report lives in that gap.

---

*All figures measured on the environment described above. Backends active for every
matcher result: BGE-M3 retrieval + lexical reranker + Ollama `qwen3:8b` + PostgreSQL
present. Working tree and database restored to their pre-test state.*
