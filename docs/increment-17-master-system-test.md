# Increment 17 — Master End-to-End System Test (Single File, All Actors, All Functionality)

## What was built

**`CareerCompassSystemTest.java`** — one file, **50 ordered test cases**, each with a
`// Purpose:` comment, run against a **real Spring Boot application context and a real H2
database** (not mocked repositories) — the only mock in the entire file is
`DataAnalysisClient`, exactly as requested, since Mohammed's Python service doesn't exist yet.

This directly answers the two things flagged as gaps in the prior conversation:
1. **Every operation is now exercised through real HTTP requests**, not just service-layer
   unit tests with mocked repositories — quiz generation, quiz submission, transcript
   confirm, job matching, and every other feature previously had unit tests only.
2. **Every actor's registration rule is explicitly tested**, matching the report exactly:
   Job Seeker and Employer self-register; Administrator, Content Manager, and Expert do
   **not** — and this is proven by hitting the actual (non-existent) register routes and
   confirming `404`, not just by reading the code.

## Structure — 10 phases, one continuous user journey

| Phase | Order range | What it covers |
|---|---|---|
| 0 | 1-4 | Reference data seeding, Administrator provisioning (no register endpoint exists), Admin login |
| 1 | 10-16 | Job Seeker: register, duplicate-email rejection, login, wrong-password rejection, view/update profile, unauthenticated rejection |
| 2 | 20-25 | Employer: register (x2, for later ownership tests), post job, update own job, cannot update another employer's job (403), role-cross-check |
| 3 | 30-39 | Content Manager & Expert: confirms no register endpoint for either, Admin creates both, both can then log in, Expert activates for consulting, Content Manager selects study field and uploads a learning-outcome PDF (+ rejects non-PDF) |
| 4 | 40-42 | Transcript upload (nothing persisted yet) -> confirm (persists + computes skill vector/gap via mocked AI) -> dashboard re-fetch |
| 5 | 50-51 | Course recommendation generation and re-listing (demonstrating the Increment 11 schema-limitation behaviour live) |
| 6 | 60-62 | Quiz generation (asserts the raw JSON never contains `correctOption`), submission with correct scoring, direct database verification that the FR-JS-20 write-back actually changed the persisted skill score, and duplicate-submission rejection |
| 7 | 70-77 | Mentor browsing, booking, Expert scheduled-session view, an unrelated Expert is rejected (403) from viewing the job seeker's data, accept request, the related Expert then succeeds, outcome recording, consultation history |
| 8 | 80-82 | Job Seeker's matches, Employer's matched candidates (with skill insights + email for FR-EMP-13), a different employer is rejected (403) |
| 9 | 90-93 | Admin deactivates the Content Manager (who then cannot log in), Job Seeker deletes their own profile (verified against the database that every dependent table was actually cleared), and the old JWT can no longer retrieve a profile that no longer exists |

## Key things this test proves that no prior test did

- **The `correctOption` field is never sent to the client during a quiz attempt** — checked
  by asserting the literal string `"correctOption"` does not appear anywhere in the raw JSON
  response body, not just by trusting the DTO's field list.
- **The quiz write-back (FR-JS-20) genuinely changes the database.** Phase 4 sets "Operating
  Systems" to a grade-derived score of 55. Phase 6 has the job seeker score 50% on a quiz for
  that exact course. The test then queries `JobseekerSkillRepository` directly and asserts the
  score is now **50.00**, not 55 — this is the single most important behavioural guarantee in
  the whole quiz feature, and it had never been checked at this level before.
- **Ownership and relationship gating hold under real requests with real tokens**, not just
  mocked `UserPrincipal` objects: a second Employer genuinely cannot touch the first
  Employer's job or view its candidates; a second Expert genuinely cannot view a job seeker's
  data until an appointment actually exists between them.
- **Account deactivation actually blocks login** (Content Manager, Phase 9) — not just a flag
  that's set but never checked.
- **Deletion is real, not soft** — after the Job Seeker deletes their profile, the same
  (still-valid) JWT can no longer retrieve anything, because the underlying row is gone, and
  every dependent table (academic records, skills, quizzes) is verified empty directly against
  the database.

## Honest limitations — please read before trusting this

- **I could not run `mvn test` in this environment.** Maven is not installed in this sandbox
  and Maven Central is not reachable from it. Every line of this test was written and
  reasoned through carefully against the actual current DTOs, entities, and controller
  signatures in your codebase — including catching and fixing a real bug myself during
  writing (a `BigDecimal.valueOf(82)` vs `82.0` serialization mismatch that would have failed
  a JSON assertion) and a missing Hamcrest import — but **you must run it yourself**:
  ```bash
  mvn test -Dtest=CareerCompassSystemTest
  ```
  If it fails to compile or fails an assertion, that's the expected next step — please treat
  this as a strong first draft that needs your own verification pass, not as something
  already confirmed green.
- **State is shared across all 50 test methods on purpose** (`@TestInstance(PER_CLASS)`),
  meaning they must run in the declared `@Order` sequence and cannot be run individually out
  of order without failing (e.g. you cannot run the "submit quiz" test alone — it depends on
  the quiz having been generated by an earlier test in the same run). This is a deliberate
  trade-off for testing a realistic user journey; it is not a substitute for the independent,
  isolated unit tests from Increments 3-16, which remain valuable for exactly the cases where
  independent, order-agnostic tests are what you want.
- **File uploads write real (small, fake) files to `./uploads/learning-outcomes/` on disk**
  during the test run, since `FileStorageService` isn't mocked here — harmless, but you may
  want to clean that directory after running tests, or add it to `.gitignore` if not already
  covered.
- **This test does not replace Increments 3-16's unit tests** — it complements them. The unit
  tests verify each piece in isolation with fine-grained control over edge cases (e.g.
  malformed AI responses, every exception type); this test verifies the pieces work together
  as a real system. Both kinds of coverage matter for different reasons.

## Setup steps for you

1. Run it:
   ```bash
   mvn test -Dtest=CareerCompassSystemTest
   ```
2. If any single step fails, the ordered structure and phase comments should make it very
   fast to identify exactly which functionality broke and why — each phase is self-contained
   and clearly labeled.
3. Run the full suite (this test plus all 16 prior increments' tests) together:
   ```bash
   mvn test
   ```
