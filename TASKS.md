# CareerCompass — task queue

Small, self-contained tasks. Each one names the files, the change, and how to prove it worked.
Do them in order where a dependency is stated; otherwise they are independent.

**Rules that apply to every task**

- Leave the work in the working tree. **Do not commit.**
- Backend needs JDK 17 explicitly — this machine defaults to JDK 25:
  `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 mvn -o test`
- AI-service tests are self-running scripts, not pytest:
  `cd ai-service && PYTHONPATH=src python3 -m tests.test_skill_gap`
- Frontend checks: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run lint && npm run build`
- Full stack: `docker compose up --build -d` → frontend :5173, backend :8080, ai-service :8000
- Demo login: `student@demo.local` / `student12345`

---

## Why the first three tasks exist

Only **20 course syllabi** have ever been extracted into `ai-service/data/extracted/skills/`.
Measured against the career-path ontology, that caps *any* student at 35–47% of a path's
technical requirements — the rest render as "Missing" no matter what they studied.

`ai-service/data/mock/` holds 96 more already-extracted skill maps (synthetic, LLM-written) plus
a matching 41-course transcript. Loading them takes every path to 84–93%. Verified: identical
file shape, same `taxonomy_version: 1.0`, all 299 skill ids resolve against the taxonomy, zero
overlap with the real 20.

Tasks 1–3 wire that in **and keep it honestly labelled**, which is the whole condition of using it.

> ## ⚠️ Two agents are editing this repo
>
> An `_with_coverage` implementation in `ai-service/src/careercompass/api/app.py` was replaced
> mid-session, dropping the per-student synthetic count and substituting the size of the whole
> mock corpus (96 — the same number for every student). It has been restored. If you are working
> here alongside another agent, **re-read a file before editing it**, and check `git diff` before
> assuming your own change is still in place.
>
> **T0 below was added after T1–T9 were written.**
>
> **T1–T6 are implemented and verified.** Left in the working tree, uncommitted. Measured on the
> demo student: readiness 0% → 18%, Strong skills 0 → 18, and the page now states that 28 of
> their 35 courses were readable and that 23 of those use synthetic syllabi.
> T4–T6 were done by another agent and verified here.
> **Start at T7.**

---

## ~~T0 — `required_level` was saturated at "advanced"~~ ✅ DONE

Recorded because the reasoning matters more than the diff.

`required_level` sets the bar the gap analysis classifies every skill against (`advanced` → 0.85
proficiency and 1.00 evidence coverage). It read `advanced` on **83.4%** of requirements, against
a corpus where only 51% of skill mentions were advanced — so the level had stopped distinguishing
anything, and every student appeared further behind than they were.

The cause was a **double mode**. `job_corpus._modal_level` collapses each term to a single level
for the `job_skills` row it becomes, and `ontology` then took a mode of those modes. Each stage
pushed toward the largest bucket:

| | beginner | intermediate | advanced |
|---|---|---|---|
| what postings actually asked for | 9% | 40% | 51% |
| after the per-term mode | 2% | 33% | 65% |
| after a second mode | 0.5% | 16% | **83%** |
| **now — weighted median** | 0.5% | 40% | **59%** |

Fixed by carrying each term's full `levels` distribution through `to_skills` and taking the
**weighted median** in `ontology._required_level` — the depth that satisfies half the market,
which is what a requirement means. Rebuilt offline with
`python -m careercompass.cli.extract_job_skills --reuse-pool --resume` (no LLM, no re-scrape).

191 of 771 rows changed level. `coverage` and `posting_count` are unchanged on every row, so the
demand side is untouched. Three tests added to `tests/test_job_corpus.py` — the ontology's level
aggregation had **no test coverage at all**, which is why nothing failed while it was wrong.

**Postgres `career_path_skills` is now stale.** The rebuild wrote the JSON the runtime reads, but
`--db` was not passed. Re-run with `--db` if anything starts reading that table.

---

## ~~T1 — Load the mock course corpus behind a flag~~ ✅ DONE

**Value: high.** Raises requirement coverage from ~40% to ~88%.

**Files**
- `ai-service/src/careercompass/config.py`
- `ai-service/src/careercompass/api/app.py` (function `_course_skill_map`, ~line 868)
- `compose.yaml` (ai-service `environment:`)

**Do**

1. In `config.py`, beside `SKILLS_DIR`, add:
   ```python
   MOCK_SKILLS_DIR = DATA_DIR / "mock" / "skills"
   # Synthetic course→skill maps, off unless explicitly asked for. Never merged silently:
   # every file in there says "Not a real MEU document" and the product must be able to
   # repeat that claim.
   INCLUDE_MOCK_COURSES = os.getenv("CC_INCLUDE_MOCK_COURSES", "0") == "1"
   ```
2. In `_course_skill_map()`, the glob that feeds `_load_course_skills` is currently
   `tuple(sorted(SKILLS_DIR.glob("*.json")))`. Extend it with the mock files when the flag is on.
   Real files must come **first** so a real course always wins a code collision (there are none
   today, but that must stay true if a real syllabus is added later).
3. In `compose.yaml`, set `CC_INCLUDE_MOCK_COURSES: "1"` on the ai-service so the demo stack has it.

**Do not** copy files into `data/extracted/skills/`. That destroys provenance and makes T3 impossible.

**Verify**
```bash
docker compose up --build -d ai-service
curl -s localhost:8000/api/v1/courses -H "Authorization: Bearer careercompass-local-dev-token" \
  | python3 -c "import sys,json; print('courses:', json.load(sys.stdin)['total'])"
```
**Done when:** total is **116** with the flag on, **20** with it off.

---

## ~~T2 — Show which courses could not be read~~ ✅ DONE

**Value: high.** Without it the dashboard blames the student for missing data.

The AI service already returns `courses_counted` and `courses_skipped`
(`[{"course_code": "9999999", "reason": "no skill map"}]`). `AiWire.java:85-86` decodes both.
Nothing carries them further. This was dropped from an earlier plan and is still owed.

**Files (in order)**
1. `backend/.../integration/dto/SkillGapAnalysisResponse.java` — add `coursesCounted` (Integer)
   and `coursesSkipped` (`List<SkippedCourse>`; add a small nested class with `courseCode`, `reason`)
2. `backend/.../integration/ai/AiWire.java` — `SkillGapResponse` already has `coursesCounted`;
   add `coursesSkipped` to it (the record for a skipped course too)
3. `backend/.../integration/ai/HttpDataAnalysisClient.java` — map both in `analyzeSkillGap`
4. `backend/.../integration/ai/MockDataAnalysisClient.java` — return empty list + a plausible count
5. `backend/.../dto/response/SkillDashboardResponse.java` — add both
6. `backend/.../service/TranscriptService.java` — copy both onto the response
7. `frontend/src/types.ts` — add to `SkillDashboardResponse`
8. `frontend/src/pages/student/DashboardPage.tsx` — render inside `SkillProfile`, using the
   existing `<details className="review-details">` idiom, near the `Provenance` card

**Wording** (do not soften it — the point is that it is not the student's fault):
> Built from 18 of your 24 courses. 6 have no syllabus extracted yet, so skills they teach may
> show as missing.

**Verify**
```bash
T=$(curl -s -X POST localhost:8080/api/auth/job-seekers/login -H 'content-type: application/json' \
  -d '{"email":"student@demo.local","password":"student12345"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s localhost:8080/api/job-seekers/me/skill-dashboard -H "Authorization: Bearer $T" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('coursesCounted'), d.get('coursesSkipped'))"
```
**Done when:** both fields are non-null in the JSON and the `<details>` appears on the page when
`coursesSkipped` is non-empty (and is absent when it is empty).

---

## ~~T3 — Label the synthetic courses in the UI~~ ✅ DONE

**Depends on T1 and T2.** This is the condition attached to T1, not an optional polish.

Every mock file carries `"mock": true` and a `WARNING` field. The product must repeat that.

**Files**
- `ai-service/src/careercompass/api/app.py` — count how many of the loaded course maps came from
  `MOCK_SKILLS_DIR`; add `synthetic_course_count` (int) to the `SkillGapResponse` payload
- `ai-service/src/careercompass/api/schemas.py` — add the field to `SkillGapResponse`
- `docs/contracts/careercompass-ai-internal-v1.yaml` — add it to the `SkillGapResponse` schema
- Then the same passthrough chain as T2 (AiWire → DTO → dashboard DTO → types.ts → page)

**Wording:**
> Demo data: 41 of these courses use synthetic syllabi, not real MEU documents.

**Done when:** with `CC_INCLUDE_MOCK_COURSES=1` the notice is visible on the dashboard, and with
the flag off it does not render at all.

---

## ~~T4 — Remove the dead narrative paragraph~~ ✅ DONE

**Value: low effort, removes a lie.** `DashboardPage.tsx` renders `data.narrative`, but
`TranscriptService.java:244-248` never sets `includeNarrative`, so it is always null.

Two options — **pick removal** unless the LLM is known to be configured:

- **Remove:** delete the `{data.narrative && ...}` block from `DashboardPage.tsx`. Leave the
  field on the DTOs; the contract supports it and a later task can turn it on.
- **Enable:** add `.includeNarrative(true)` in `TranscriptService`. Costs an LLM call on every
  dashboard load, and returns null anyway unless the AI service has a model configured
  (`CC_MATCH_LLM=1`). Do not do this without measuring the added latency.

**Done when:** the page has no branch that can never be true.

---

## ~~T5 — Add three missing CSS rules~~ ✅ DONE

**Value: cosmetic, 15 minutes.** Three classes are used in TSX with no rule in `index.css`, so
they render unstyled.

| Class | Used in |
|---|---|
| `.mentor__match` | `frontend/src/pages/student/MentorsPage.tsx` |
| `.outcome__status-copy` (and `--error`) | `frontend/src/pages/content/LearningOutcomesPage.tsx` |
| `.outcome__actions` | `frontend/src/pages/content/LearningOutcomesPage.tsx` |

Use existing tokens only (`--text-muted`, `--danger`, `--border`, …). `index.css` states that
nothing below `:root` hard-codes a colour — keep that true.

**Done when:** `npm run build` passes and each class has a rule.

---

## ~~T6 — Delete committed build artifacts~~ ✅ DONE

**Value: tidiness, 5 minutes.**

`frontend/build-errors.txt` (413 B) and `frontend/fix_ts.js` (2.4 KB) are leftovers from a past
fix-up, not part of the app, and are not gitignored.

Delete both; add `build-errors.txt` to `frontend/.gitignore`.

**Done when:** `npm run build` and `npm run lint` still pass.

---

## T7 — Make the pytest suites runnable

**Value: unblocks 3 test files.** `pytest` is not installed in the active venv, so
`tests/test_api_auth.py`, `tests/test_content_manager_api.py` and `tests/test_mentor_matching.py`
cannot run at all — they fail with `ModuleNotFoundError: No module named 'pytest'`.

Install it into the environment the project actually uses (`.venv` at the repo root), and
record the command in `ai-service/README.md` next to the existing test instructions.

**Done when:** `cd ai-service && PYTHONPATH=src python3 -m pytest tests/ -q` runs and reports
results. Fix any genuine failures it surfaces, or list them — do not delete tests to go green.

---

## T8 — Code-split the charts

**Value: bundle size.** Adding recharts took the production bundle to **737 KB** (214 KB gzipped),
and it is only used on one page.

Load `frontend/src/components/charts.tsx` via `React.lazy` + `<Suspense>` from
`DashboardPage.tsx`, using the existing `<Skeleton />` as the fallback.

**Done when:** `npm run build` shows the main chunk materially smaller and a separate chart chunk,
and the dashboard still renders its charts.

---

## T9 — Mentor match score scale (read the warning first)

**Value: consistency. Trap: do not half-fix this.**

ADR-003 fixes scores at 0–100 on the Java side. `matchScore` is the one exception:
`HttpDataAnalysisClient.java:560` passes the AI service's 0.0–1.0 value straight through instead of
using `toPercent()`, and `MentorSummaryResponse.matchScore` is a raw `Double`.

`MentorsPage.tsx:104` multiplies by 100 — **which is correct today.** Changing either side alone
breaks the display.

If you take this: change `HttpDataAnalysisClient` to use `toPercent(...)`, change the DTO to
`BigDecimal`, and remove the `* 100` in `MentorsPage.tsx` — **in one change**. Otherwise leave it
alone and it stays correct.

**Done when:** the mentors page shows the same percentage it does now.

---

## Not simple — do not start these without scoping

- **Job matching is dead against the real AI service.** `HttpDataAnalysisClient.java:515` throws
  `501 AI_CAPABILITY_NOT_IN_SCOPE`; the student Jobs page only works with
  `careercompass.ai-service.use-mock=true`. Implementing it is a new AI module, not a task.
- **`--warn` and `--danger` are indistinguishable under deuteranopia** (ΔE ≈ 1.3 measured). The
  app compensates by always pairing status colour with a text label, so nothing is broken today,
  but the tokens themselves want re-stepping — and that touches every page.
