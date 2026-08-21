# CareerCompass — Engineering Notes

The durable facts, in one place: the things that are true about this system
regardless of which session discovered them, and the mistakes expensive enough
that repeating them should be impossible.

The dated session reports this replaced have been removed; what was still true
from them lives here.

**Last updated:** 20 August 2026

Contents:

1. [What the system does](#1-what-the-system-does)
2. [The identity problem, three times over](#2-the-identity-problem-three-times-over)
3. [Course codes are not course identity](#3-course-codes-are-not-course-identity)
4. [Failures that look like successes](#4-failures-that-look-like-successes)
5. [Noise terms: the filter that only catches what you name](#5-noise-terms-the-filter-that-only-catches-what-you-name)
6. [Numbers that were measured, not assumed](#6-numbers-that-were-measured-not-assumed)
7. [How the weights and scores work](#7-how-the-weights-and-scores-work)
8. [Hardware reality on this machine](#8-hardware-reality-on-this-machine)
9. [Data layout and what must never be committed](#9-data-layout-and-what-must-never-be-committed)
10. [Mock data rules](#10-mock-data-rules)
11. [Configuration](#11-configuration)
12. [Tests](#12-tests)
13. [Open decisions](#13-open-decisions)
14. [What automated checks cannot catch](#14-what-automated-checks-cannot-catch)

---

## 1. What the system does

A skill gap is a subtraction between two tables. Everything else is machinery
for filling them honestly.

```text
SHARED, uploaded once            PER-STUDENT
syllabus of course X             transcript: "I took X, grade A-"
        │                                 │
        └──── course → skill map ─────────┘
                        │
              Student Skill Vector (M2)
                        │
        compare against career_path_skills
              (mined from 2,238 job postings)
                        │
                   Skill Gap (M3)
```

**Syllabi are not per-student.** They are shared knowledge-base content,
uploaded once by a content manager. Two students on the same plan get different
skill vectors because they took different electives and earned different grades,
not because they hold different syllabi. This is the single most common
misunderstanding of the design.

| Module | State |
|---|---|
| M1 Transcript analysis | built |
| Syllabus → skill pipeline | built |
| Job → skill pipeline + career-path ontology | built, 771 requirements over 9 paths |
| **M2 Skill vector** | **built, 20 Aug** |
| M3 Skill gap | not started, unblocked |
| M4 Courses · M5 Quiz · M6 Matching | not started, all behind M3 |

---

## 2. The identity problem, three times over

One mistake, three costumes. Every occurrence was silent, and every one made a
student look like they lacked something they had.

| Where | What went wrong | Fix |
|---|---|---|
| Taxonomy (18 Aug) | ESCO's `Java (computer programming)` and custom `Java` were two ids for one skill. Label-based dedupe cannot catch it — the labels differ | `merge_skills` folds on the qualifier-stripped label |
| Job ontology (18 Aug) | `Grafana`, `Prometheus`, `logging`, `monitoring` all resolve to one skill; their posting counts were **summed**, putting it at 100% of the DevOps path | numerator is a **union of posting ids** |
| M2 skill vector (20 Aug) | `derivatives`, `integration`, `limits` all resolve to `calculus`; their weights were **summed**, so a course phrasing a topic ten ways outweighed one phrasing it once | weights are **maxed within a course**, not added |

What the ontology fix changed, in the numbers `required_score` reports and M3
subtracts against:

| Skill | Before | After |
|---|---:|---:|
| monitoring and observability | 100.0 | 51.9 |
| Terraform | 81.1 | 48.1 |
| secure coding practices | 56.8 | 47.3 |

The shape to watch for: **many-to-one resolution followed by an aggregate.**
Whenever N things collapse to one canonical id and you then count, sum or
average, ask what happens when several of the N land in the same document.

The taxonomy case had already reached the database. Five `course_skills` rows
pointed at retired ids. `db.skills.remap_retired_skills` repoints stored rows
through the current alias index and runs automatically under `--db` — but a
merge always leaves written rows behind, so this must run after any merge.

**And it only ever repaired half the system.** The database was fixed; the JSON
artefacts were not, and `data/extracted/skills/*.json` is what every API path
actually reads. `custom:java` (4 rows) and `custom:python` (1) survived there
until 21 August, so a student graded **A** in Object Oriented Programming in
Java joined against nothing and was reported as having a complete Java gap —
the same defect this section is about, hiding one directory away. Python is the
top requirement of the AI & ML path at 46%, and it failed the same way.

**A merge is therefore three steps, not two:**

```bash
python -m careercompass.cli.build_taxonomy                    # 1. merge
python -m careercompass.cli.remap_extracted_skills --dry-run  # 2. repair the JSON
python -m careercompass.cli.extract_job_skills --db           # 3. repair the database
```

`skills.vector.load_course_skills` now also resolves every `canonical_id`
through the alias index as it loads, and logs a warning naming the course and
term when one no longer resolves. Step 2 keeps the files correct; the load-time
pass is what stops the next merge from being silent.

---

## 3. Course codes are not course identity

The newer plan editions renumbered their courses. A code identifies a course
*within one plan edition* and nowhere else.

**24 course numbers mean different courses in different plans:**

```text
0181503  CS, CS/AI    Programming Fundamentals
A0181503 CYBER        Digital Logic              ← not the same course

0433301  CS, CS/AI    Operating Systems
A0433301 CYBER        Application Security       ← not the same course

0412401  CS, CS/AI    System Analysis and Design
A0412401 CYBER        Database Systems           ← not the same course
```

**Stripping the letter prefix does not merely fail to merge — it actively merges
unrelated courses.** This was demonstrated twice on tooling built for this
project, both times silently:

- the checklist generator first grouped on the prefix-stripped code, merging
  Programming Fundamentals with Digital Logic;
- its collection-status check canonicalised codes before comparing and marked
  **Database Systems as extracted** when no such syllabus existed, because
  `A0412401` strips to `0412401`, which *is* extracted as System Analysis and
  Design.

Two consequences that are already load-bearing:

- `data/plans/required_syllabi.md` groups by **normalised course name**, which
  over-splits at worst rather than joining wrongly.
- `skills/vector.py` accepts a `course_codes` list per transcript row, so a
  transcript quoting `0433301` still resolves against a map holding `A0413301`.

**The mapping does not have to be guessed.** Some syllabi print both schemes:

```text
Course No.    A0413301 (0433301)
Pre-requisite A0412101 (0432101) - Data Structures
```

`build_syllabus_list` harvests every such pairing into a table. The canonical
course id can be built from the department's own documents.

**The retired Cyber Security plan must not be deleted.** For several courses it
is the only document linking the two numbering schemes. Removing it from the
generator orphaned two syllabi already in hand.

---

## 4. Failures that look like successes

Three separate resource failures have exited `0` with plausible output while a
stage was silently dead. This is the dominant failure mode of the system and it
is worth actively designing against.

**The reranker fallback (18 Aug).** `get_reranker("auto")` caught only
`ImportError`, so a 2.1 GB model download failing looked like a missing
dependency. The fallback moves the accept threshold from **0.72 to 0.62** — the
system quietly became more permissive. A recheck at `accept_score=0.95` later
overturned **98 of 268** borderline matches, 37%.

**The buffered configuration header (18 Aug).** `print()` is block-buffered when
redirected to a file; `logging` is not. The header naming the active reranker sat
unflushed for an entire two-hour run — the one line worth reading early was the
one line unreadable.

**The CUDA OOM (20 Aug).** `bge-m3` and `qwen3:8b` do not fit together on an
8 GB card. The run completed normally with one buried line:

```text
Ollama selection failed: HTTP 500: CUDA error: out of memory
ollama returned unparsable output for 'derivatives'
```

Every term silently skipped LLM disambiguation. Workaround below in
[§8](#8-hardware-reality-on-this-machine).

**The rule this suggests:** a stage that degrades should say so in the summary,
not only in a log line. A resource failure must not be able to masquerade as a
normal run.

Two silent parser defects, now fixed, had the same character — both returned
wrong data rather than raising:

- `COURSE_CODE_RE` was `^0\d{6}$`, so the Cyber Security edition-2 plan parsed
  to **zero courses with no error**. Now `^[A-Z]?0\d{6}$`.
- Some plans' PDF text layer carries no spaces, yielding
  `UniversityRequirementCompulsory`. Any caller filtering the spaced form
  dropped every course in that plan. `_normalise_category` restores spacing.

---

## 5. Noise terms: the filter that only catches what you name

`development`, `automation`, `activities` are frequent, grammatically noun
phrases, and retrieve *something* from any taxonomy:

| Term | Confidently resolved to |
|---|---|
| `development` | REST API development |
| `automation` | test automation |
| `activities` | **sommelier activities** |

They are dangerous rather than useless: being frequent they **outrank the real
skills they displace**, and a wrong canonical id is invisible once stored.

Three noise sets exist, and they are not interchangeable:

| Set | Location | Scope |
|---|---|---|
| `NOISE_TERMS` | `skills/phrases.py` | shared base |
| `JOB_NOISE_TERMS` | `skills/job_extractor.py` | posting scaffolding, EEO boilerplate, benefits, nav menus |
| `SYLLABUS_NOISE_TERMS` | `skills/phrases.py` | course scaffolding — `presentation`, `final project`, `course review` |

**`SYLLABUS_NOISE_TERMS` is exact-match only, deliberately.** A suffix rule
stripping "overview" or "introduction" would also delete
`IEEE 802.11 standards overview` and `instruction set architecture overview`,
and `code review` and `database design review` are skills outright.

**Any new corpus must be re-checked for the same pattern.** The specific words
will differ. The filter only catches what you thought to name.

---

## 6. Numbers that were measured, not assumed

Every row here replaced an estimate that was wrong.

| Claim | Estimate | Measured |
|---|---|---|
| Dedup collapses the job corpus | ~10x | **2.0x** — 228,145 mentions → 112,252 unique, 79% appear once |
| Dedup helps across syllabi | worth doing | **1.13x** — 91% of terms appear once. Not worth doing |
| Syllabus noise filter saves | ~15% | **2.3%** — a quality fix, not a speedup |
| Weight cutoff would cut work | large | **19%** at 0.7, and it removes real skills |
| GPU embedder is faster | obviously | **CPU was faster** — it stops competing for VRAM |

**What actually makes the job corpus tractable is a document-frequency cutoff,
not dedup.** At `df >= 5` the work is ~4,650 terms, and the cutoff costs nothing
that matters: a term in fewer than 5 of 2,238 postings cannot be a career-path
requirement.

The general lesson: **the obvious optimisation was wrong four times out of five.
Measure before building.**

### Current corpus figures

| | |
|---|---|
| Job postings | 2,238 across 9 career paths |
| Career-path requirements | 771, 82–105 per path |
| Taxonomy | 903 rows, 0 orphans |
| Real syllabi collected | 18 of 114 courses |
| Mock syllabi generated | **96 of 96** |
| Mock terms extracted | 7,268 (76/course) |
| Mock accepted / review / no match | **45% / 20% / 35%** |
| Distinct taxonomy ids exercised | 299 of 903 (33%) |

Match rate varies enormously by course, and correctly so — the taxonomy came
from job postings, so applied courses resolve and theoretical ones do not:

```text
Robotics Programming Lab           76%
Software Engineering Fundamentals  73%
Computer Networks                  42%
Cryptography Fundamentals          41%
Theory of Computation               8%
```

The market asks people to *use* cryptography, not to prove things about formal
languages. **A low match rate on a theory course is the taxonomy being honest,
not a pipeline fault.**

---

## 7. How the weights and scores work

### Syllabus extraction

| Source zone | Base weight | Level from |
|---|---:|---|
| Course learning outcome | 1.0 | JNQF descriptor, else Bloom verb |
| Lab | 0.8 | highest level of that week's CLOs |
| Weekly topic | 0.7 | highest level of that week's CLOs |
| Description | 0.6 | beginner |

`weight = strongest source weight + 0.1 × (mentions − 1)`, capped at 1.0.

JNQF descriptor → level: Knowledge → beginner, Skill → intermediate,
Competency → advanced.

### Matching thresholds

| Reranker | Auto-accept | Review floor | Lead over runner-up |
|---|---:|---:|---:|
| Lexical | 0.62 | 0.40 | 0.05 |
| Cross-encoder | 0.72 | 0.45 | 0.05 |

An LLM result needs ≥ 0.70 reported confidence. **These are starting points, not
settled values** — the design calls for 300–500 hand-reviewed mappings to tune
them, and thousands of real decisions with scores and reasons now exist to
sample from.

Statuses: `accepted` (usable), `needs_review` (a human decides), `no_match`.

### M2 skill vector

Deterministic arithmetic, no LLM, and none may be added — the same transcript
must always produce the same numbers, because M3 subtracts against them and a
student sees the result.

```text
attainment  = grade_points / 4.0
evidence    = skill_weight × level_factor       (0.70 / 0.85 / 1.00)
proficiency = Σ(evidence × attainment) / Σ(evidence)     per skill
coverage    = Σ(evidence)                                per skill
```

**Two numbers, deliberately not collapsed into one.** An A in one course
mentioning Docker once is not a B across three courses built on it.
`proficiency` answers *how well did they do*; `coverage` answers *how much did
they study it*. M3 needs both.

Only `accepted` matches enter the vector: `needs_review` is a question, not a
fact about a student, and `no_match` has no id to join on. Unpassed and exempted
courses are excluded. Quiz results replace the grade-derived value and keep it
alongside as `proficiency_from_grades` (FR-JS-22).

---

## 8. Hardware reality on this machine

```text
NVIDIA GeForce RTX 4060 Laptop   8.2 GB VRAM
system RAM                        14 GB
llama-server (qwen3:8b)           4.5 GB VRAM + 9.1 GB system RAM
bge-m3                            ~2.3 GB
```

**`qwen3:8b` and `bge-m3` do not fit on the card together.** Always run the
matcher with the embedder on CPU:

```bash
CUDA_VISIBLE_DEVICES="" python -m careercompass.cli.<whatever> --llm
```

This costs nothing measurable. The vector index is prebuilt, so only ~76 short
query strings per course are encoded; the CPU run was *faster* than the GPU run
because it stopped competing for VRAM (80s vs 89s, 127s vs 133s).

**RAM, not VRAM, blocks parallelism.** `llama-server` holds 9.1 GB of the 14 GB,
leaving no room for a second `bge-m3`. The `--shard I/N` flag on the mock
generator is correct and unusable here.

**Model choice.** `qwen3:8b` is the router. `qwen3:4b` is faster but
**confidence-saturated — it auto-accepts bad matches**, which is worse than
slow. Do not substitute it to save time.

Measured throughput: syllabus generation ~46 s/course; extraction + matching
~104 s/course. Both stages skip work already on disk, so every long run is
resumable.

---

## 9. Data layout and what must never be committed

```text
data/
  plans/        study plan PDFs        ← GIT-IGNORED, personal data
    required_syllabi.md                ← tracked: codes and names only
  syllabi/      course syllabus PDFs   ← tracked, also the parser fixtures
  extracted/
    syllabi/    parsed syllabus JSON   ← ignored, regenerable
    skills/     matched skills JSON    ← ignored, regenerable
    jobs/       job corpus artefacts   ← ignored, tens of MB
  raw/catalog/  course catalog pulls ← IGNORED: the only place course
                                        descriptions live, and they are not
                                        ours to redistribute
  extracted/catalog/                   ← the derived index: skill ids, titles
                                        and URLs only, no descriptions
  taxonomy/
    custom_skills.json                 ← tracked, a source file
    taxonomy.jsonl, vector_index.npz   ← ignored, rebuilt
  mock/         synthetic data         ← see §10
```

**Study plans and transcripts carry a student's name, ID, advisor and full grade
history and must never reach the repository.** The rule protecting them was once
`*_plan_*_EN.pdf`, written for a filename that no longer existed — **none of the
five current plan PDFs matched it**, and they would have been committed on the
next `git add`. Now `data/plans/*.pdf` and `*_plan_*.pdf`.

Course syllabi are *not* personal and stay tracked; the parser tests use them.

Rebuild generated artefacts on a fresh clone: the ESCO cache, `taxonomy.jsonl`
and `vector_index.npz` are all ignored.

---

## 10. Mock data rules

96 synthetic courses exist under `data/mock/`, generated because M2 and M3 are
arithmetic over a join whose course side is 84% missing.

**How they were made:** an LLM writes a plausible syllabus (description, 5
Bloom-verb CLOs, 15-week plan) in the shape `parse_syllabus` produces; then
`extract_skills()` and `SkillMatcher` run over it **unchanged**. Stage 2 is
deliberately not simulated, so mock rows carry real taxonomy ids, real match
statuses and real confidence scores.

A lexical alternative was tried and abandoned: scoring taxonomy labels against
the course title gave a correct top hit and junk beneath it — Computer Networks
pulled in `Pascal`, `Prolog` and `Ruby` because they share the token "computer".
Running the real extractor avoids exactly the failure in [§5](#5-noise-terms-the-filter-that-only-catches-what-you-name).

**The one rule:** *these rows must never be loaded into the production
`course_skills` table.* Every record carries `"mock": true` and a `WARNING`
field, everything lives under `data/mock/`, and nothing in the real pipeline
reads it. Mixing mock and real rows destroys the one property that makes a gap
number trustworthy: that you can tell a code fault from a coverage gap.

Regenerate:

```bash
python -m careercompass.cli.generate_mock_skills --stage 1          # LLM writes syllabi
CUDA_VISIBLE_DEVICES="" python -m careercompass.cli.generate_mock_skills --stage 2
```

---

## 11. Configuration

| Variable | Purpose |
|---|---|
| `CC_DATA_DIR` | override the data root |
| `CC_DB_HOST` `CC_DB_PORT` `CC_DB_NAME` `CC_DB_USER` `CC_DB_PASSWORD` | PostgreSQL |
| `CC_EMBEDDING_BACKEND` | `bge` or `lexical` |
| `CC_EMBEDDING_MODEL` `CC_EMBEDDING_BATCH_SIZE` | embedder |
| `CC_RERANKER` `CC_RERANKER_MODEL` | reranker; `auto` can silently fall back — see [§4](#4-failures-that-look-like-successes) |
| `CC_MATCH_LLM` `CC_MATCH_LLM_PROVIDER` `CC_MATCH_MODEL` | LLM stage |
| `CC_OLLAMA_URL` `CC_OLLAMA_TIMEOUT` | Ollama |
| `CUDA_VISIBLE_DEVICES=""` | **not optional on this machine** — see [§8](#8-hardware-reality-on-this-machine) |

Key CLI entry points:

```bash
python -m careercompass.cli.build_syllabus_list      # regenerate the checklist
python -m careercompass.cli.extract_skills <pdf> --match
python -m careercompass.cli.extract_job_skills --llm --recheck --db --resume
python -m careercompass.cli.generate_mock_skills
```

---

## 12. Tests

No pytest. Each suite is a script with a `check()` helper that records failures
instead of stopping, so one run shows every failure.

| Suite | Checks | Covers |
|---|---:|---|
| `test_syllabus_parser` | 65 | MEU syllabus structure |
| `test_skill_extractor` | 82 | phrase mining, weights, levels |
| `test_skill_matcher` | 232 | retrieval, reranking, LLM routing |
| `test_job_extractor` | 56 | posting → skills |
| `test_job_corpus` | 41 | pooling, cutoff, ontology arithmetic |
| `test_transcript_parser` | 37 | both code schemes, both spacings |
| `test_skill_vector` | 39 | M2 arithmetic, double-count guard, determinism |
| `test_skill_gap` | 49 | M3: target from level not score, priority, soft-skill ranking |
| `test_skill_quiz` | 74 | M5: question validation, self-check, grading, write-back |
| `test_course_recommend` | 38 | M4: head-noun aliases, title provenance, level fit, real URLs |

```bash
python -m tests.test_skill_vector          # one suite
```

`test_skill_matcher` builds a `SkillMatcher` and loads the embedder — do not run
it alongside a generation job on this machine.

Test fixtures live in `data/syllabi/`, not `tests/fixtures/`. The plan PDFs
cannot be fixtures (personal data), so `test_transcript_parser` drives the
row-level helpers directly.

---

## 12b. The API layering decision

Two API documents exist and they are **different layers, not competitors**. This
was settled on 18 August and should not be relitigated.

`API_DESIGN.md` is the stronger artifact — RFC 9457 errors, async job envelopes,
requirement traceability, and it resolves three contradictions in the
requirements. But it was written assuming **one service**, so most of it (auth,
profiles, employer, mentor, admin) belongs to the Java side under the agreed
split.

The Java team's service contract correctly scopes the AI service but is weaker,
and has one flaw that will break in practice: **it is synchronous everywhere
with a 30 s timeout, while syllabus extraction measures ~90 s.** `API_DESIGN.md`
already solved this with `202` plus a job resource, and the code implements it
that way.

**The decision:** hand `API_DESIGN.md` to the backend owner as the platform
spec; adopt the contract as authoritative for what FastAPI exposes to Java, with
three amendments —

1. async `202` for anything over the timeout;
2. a syllabus extraction endpoint (the course → skill map has no way into the
   system without one);
3. the three gaps the contract itself flags: error schema, service-to-service
   auth, contract test.

The contract's **"names, not IDs"** rule is right and was kept:
`career_path_skills` keys on the career-path *name*, never on Java's numeric id.

---

## 12c. Operational habits that were learned the hard way

**Checkpoint long runs.** Job matching checkpoints every 50 terms and resumes;
the mock generator and batch syllabus extraction skip anything already on disk.
Any run measured in hours must be resumable, because it will be interrupted.

**Size text columns for the worst case, not the common one.**
`job_skills.sources` was `VARCHAR(40)`; the string
`responsibilities+requirements+qualifications` is 44 characters, and the insert
crashed after the expensive work was done. It is now `VARCHAR(120)`, matching
`course_skills`.

**Share one database connection across a batch.** `store_job_skills` opened its
own connection per posting — 2,238 connect/close cycles. Sharing one brought the
full persist to 32 s.

**Build heavyweight objects once.** A recheck pass constructed a second
`SkillMatcher`, loading a second bge-m3 into the same process and OOMing the
card. `SkillMatcher.with_thresholds()` shares the loaded index and model; the
batch CLIs build one matcher and reuse it.

---

## 12d. Catalog sourcing, and the licence boundary

M4 recommends real courses, which makes it the one module where invented data
is directly harmful: a wrong skill match is invisible, but a dead course link
is something the student clicks. It therefore could not be filled synthetically
the way the missing syllabi were.

**Sources, checked rather than assumed (August 2026):**

| Source | Access | Terms |
|---|---|---|
| Coursera `api.coursera.org/api/courses.v1` | **Public, no key**, 23,564 courses | Beta, may break without warning. Catalog copyright belongs to university partners; **no licence to republish** descriptions |
| MIT Learn `api.learn.mit.edu` | Public, 3,002 courses | States `license_cc` per record. Mixes CC-licensed OCW with non-CC xPRO and MITx |
| YouTube Data API v3 | Official, 10k units/day free | `search.list` costs 100 units, so ~100 searches a day |
| **Udemy** | **Affiliate API discontinued 1 January 2025** | No sanctioned programmatic access remains |

**Do not scrape.** Coursera needs no scraping — its own API returns everything
required. Udemy cannot be scraped usefully: its terms forbid it and the site is
behind bot protection, so a scraper would be both a breach and permanently
broken. Udemy is simply out.

**The licence boundary, and where it is enforced.** Descriptions are fetched,
read once to derive skill tags, and dropped. Only skill ids, title and URL are
persisted. Three places enforce it and all three carry the reason in a comment:
`skills/course_index.build_index` (which never copies the field),
`005_course_catalog.sql` (which has no description column and says one must not
be added), and `.gitignore` (which excludes `data/raw/catalog/`, the only place
descriptions live).

The `explanation` a student reads is generated from **their own gap**, never
from the course page. That is a licence rule and also better advice: "the
container work your coursework never covered, asked for by 18% of postings"
says something the course's marketing copy cannot.

---

## 12e. Why M4 does not use the skill matcher

The obvious design was to mine terms from course text and resolve them with
`SkillMatcher`, exactly as the job corpus does. The arithmetic rules it out:
23,564 courses yield roughly 235,000 terms, and at the measured ~1.7 s per
LLM-routed term that is over 100 hours. The job corpus made itself tractable
with a document-frequency cutoff, but a cutoff is precisely wrong here — a
course teaching a niche skill is exactly what is worth recommending, and
`df >= 5` deletes it.

So the direction is reversed. Rather than "what does this text mention, and
which skill is that?", M4 asks "which of the known skills does this text
name?" — an exact lookup against the taxonomy's labels and aliases. It runs in
seconds, needs no model, and cannot invent a mapping.

**It trades recall for precision on purpose.** A course whose description says
"containerisation" in words the taxonomy does not list is missed. But a course
is never tagged with a skill it does not name, and for recommendation that is
the right way round: a missing course is invisible, while a wrong one is
something the student works through and does not get the skill from.

Three defects surfaced while tuning it, all the same family as
[§5](#5-noise-terms-the-filter-that-only-catches-what-you-name):

- **`packaging engineering` ranked third** in a catalog of computing courses,
  because ESCO lists `engineering` among its aliases. Fixed with a rule rather
  than a word list: *a single-word alias that is one of the words of its own
  multi-word label is a head noun*, and a head noun never identifies a skill.
  `Access` for Microsoft Access and `communication` for communication skills go
  the same way, while `Docker`, `ML`, `K8s` and `Jenkins` all survive.
- **`Design Patterns` was tagged as manufacturing dies**, because `patterns` is
  an ESCO alias for it. Fixed by indexing only the ~213 skills some career path
  actually requires: a gap can only ever contain those, so every alias outside
  that set is pure false-positive surface.
- **`HTML5: Content Authoring Fundamentals` was offered as a way to learn
  Linux**, because its description said it runs on Linux. Tags now record
  whether the skill appeared in the **title** or only the description, and a
  passing mention ranks far below a course that is actually about the subject.

**A ranking that saturates is not a ranking.** The first scorer multiplied a
title-match bonus into the total, pushing most results past 1.0 where they were
clipped — every recommendation displayed `relevance: 1.000`. Relevance is now a
bounded sum of three terms (is it about the skill, is it the right level, does
the market want it), and *which skill to address first* is a separate question
answered by the gap's own priority.

---

## 13. Open decisions

**The canonical course id.** Nothing has been decided. It must be settled
*before* more syllabi are extracted — retrofitting means re-extracting
everything. See [§3](#3-course-codes-are-not-course-identity); the harvested
equivalences give a starting set backed by the department's own documents.

**`skill_type` on `career_path_skills`.** Soft skills — `communication skills`,
`problem solving` — rank top-3 in nearly all nine career paths. That is an
accurate reading of job postings, but it means they cannot differentiate paths,
and a dashboard ranking them first gives every student the same advice. The
taxonomy already carries `skill_type`; the ontology table does not surface it.
**Add this before M3.**

**Threshold tuning.** The review queue now holds thousands of real decisions with
scores and reasons. Harvesting 300–500 into a labelled set is the prerequisite
for both tuning and any hybrid reranker.

**Two-letter names are dropped.** `MIN_TERM_LENGTH` is 3, so `Go`, `R` and `C`
never reach the matcher. Pinned in a test so it is visible rather than
surprising.

**2,526 mock terms and 2,679 job terms found nothing.** That is not only
failure — it is the record of what a 903-skill vocabulary is missing for this
market, and it is worth mining to extend the taxonomy.

**The backend contract does not match the code.** Five of the six endpoints in
the Java team's service contract do not exist, and the sixth differs in path,
payload and response shape. This is a conversation, not code, and it has been
outstanding since 18 August.

**Work is left uncommitted by standing preference.** The user reviews and
commits their own work; do not run `git commit` or `git push`.

---

## 14. What automated checks cannot catch

Three outputs now reach a student directly, and for each there is a class of
error no test in this repository can detect. Worth naming, because the passing
suites make it easy to forget.

**A quiz key can be confidently wrong.** M5 validates structure — four distinct
options, a valid index, no duplicate questions, no two options that are the same
number — and then asks the model to answer its own questions and drops any it
contradicts. A generated question still asked *"What is the primary purpose of
cross-validation?"* and keyed **"To reduce overfitting"**. Cross-validation is
an evaluation technique: it detects overfitting, it does not reduce it. The
question is structurally perfect and the model agrees with itself. A student who
genuinely understands CV hesitates, and the score overwrites their proficiency.

**Two questions can test one fact.** The same quiz asked which algorithm is
supervised and which is unsupervised, both hinging on K-means. A four-question
quiz measuring three things is noisier than its length suggests. Text overlap
between the two was 0.73 against a 0.80 threshold — close enough that lowering
the bar would start rejecting good questions.

**A URL that is a non-empty string is not a working link.** M4 tests assert
every item carries a URL, which is not the same as the page existing. A course
withdrawn from a platform keeps its slug.

**So: read the output.** Generate a quiz for a skill you know well and check the
keys by hand. Open a sample of recommended courses. Do it again after any
Coursera API change, since that endpoint is documented as beta and free to break
compatibility without warning.

---

## Related documents

| Document | Covers |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | module-by-module build state |
| [API_DESIGN.md](API_DESIGN.md) | platform-wide interface, five actors, six modules |
| [SKILL_EXTRACTION_API.md](SKILL_EXTRACTION_API.md) | the skills subsystem as implemented |
| [SYLLABUS_SKILL_EXTRACTION.md](SYLLABUS_SKILL_EXTRACTION.md) | syllabus pipeline internals |
| [JOB_SKILL_EXTRACTION.md](JOB_SKILL_EXTRACTION.md) | job pipeline internals |
| `data/plans/required_syllabi.md` | the live syllabus collection checklist |
