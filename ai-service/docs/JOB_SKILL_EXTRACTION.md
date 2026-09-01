# CareerCompass Job Skill Extraction and the Career-Path Ontology

## Purpose

The syllabus pipeline builds the left half of the gap analysis: what a course
teaches. This one builds the right half: what a career path demands, derived
from 2,238 scraped LinkedIn postings across nine paths rather than from anyone's
opinion.

Both sides resolve onto the same taxonomy, so a course that teaches
`Developing ROS 2 Nodes` and a posting that asks for `ROS 2 node development`
compare as one skill, and a gap is a subtraction.

```
postings ──► extract ──► pool ──► cutoff ──► match once ──► aggregate ──► ontology
             per job    corpus    df >= 5    per term       per path
```

## Why a posting is harder than a syllabus

A syllabus is a form. A posting is a web page someone wrote in a hurry, and the
most repeated text in the corpus is not skills at all. Measured over all 2,238:

| Kind of noise | Scale before filtering |
|---|---|
| Section headings read as terms | `responsibilities` ×960, `qualifications` ×501, `requirements` ×494 |
| EEO legal boilerplate | in 483 postings — `religion` ×328, `sexual orientation` ×305 |
| Benefits sections | `dental` was the 102nd most common term |
| Whole scraped web pages | navigation menus captured with the body |
| Recruiting padding | `strong X skills`, `5+ years of experience in X` |

Left alone these are the *strongest* signals in the corpus, so the ontology
would describe recruiting prose rather than skills. The extractor therefore
finds the structure first and cuts the noise before mining any phrase.

## The cutoff, and why dedup is not enough

The original plan assumed global deduplication would make matching feasible.
Measurement showed otherwise:

| Metric | Measured |
|---|---|
| Term mentions across the corpus | 228,145 |
| Unique terms after dedup | 112,252 |
| Dedup ratio | **2.0x**, not the ~10x assumed |
| Unique terms appearing exactly once | 89,051 (79%) |

Halving the work is not enough. What makes the corpus tractable is **document
frequency** — and the cutoff costs nothing that matters, because a term
appearing in fewer than five of 2,238 postings cannot be a career-path
requirement, so it cannot change the ontology this feeds.

| Cutoff | Terms to match | Roughly |
|---|---|---|
| all | ~91,000 | infeasible |
| `df >= 3` | ~9,000 | ~5 h |
| **`df >= 5`** | **~4,650** | **~2.5 h** ← default |
| `df >= 10` | ~1,850 | ~1 h |

Frequency is counted **per posting, never per mention**: a posting that says
"Kubernetes" six times wants Kubernetes once, and counting mentions would let
one verbose employer outvote fifty concise ones.

## Stages

### 1. Extract — `skills/job_extractor.py`

Routes each line into a zone, then mines phrases from the zones that carry
skills.

| Zone | Weight | |
|---|---|---|
| `title` | 1.0 | stripped of seniority: "Senior Backend Engineer II" → "Backend Engineer" |
| `requirements` | 1.0 | the direct statement of what is needed |
| `qualifications` | 0.9 | including "nice to have" |
| `responsibilities` | 0.7 | skills implied by tasks, not stated |
| unlabelled prose | 0.5 | recall, low precision |
| `benefits`, `about us`, `perks` | — | **dropped whole** |

Benefits are dropped as a section rather than filtered term by term, because a
benefits list is uniform prose that no term-level rule separates reliably from a
requirements list.

**Refinement** then collapses variants rather than dropping them, which is what
turns four weak signals into one strong one:

| Written as | Becomes |
|---|---|
| `strong communication skills` | `communication` |
| `5+ years of experience in Kubernetes` | `Kubernetes` |
| `Proficiency in Python` | `Python` |
| `Design, develop and maintain APIs` | `APIs` |

Measured effect: `communication` went from 116 to 569 postings, `Python` from
338 to 483.

**Level** is what the posting asks for, not what it teaches. LinkedIn's
`seniority_level` is authoritative but present on only 43% of the corpus, so the
title carries the rest (`senior|lead|principal` → advanced, `junior|intern` →
beginner).

### 2. Pool — `skills/job_corpus.py`

Collapses the corpus into one record per term: document frequency, a per-path
breakdown, the modal level, and up to three pooled evidence lines drawn from the
strongest zone across *different* postings.

Pooled evidence beats any single posting's. `Java` retrieved alone is ambiguous;
`Java` plus the three most authoritative lines any employer wrote about it is
not.

A term's level is the **mode, not the maximum**. Over 2,238 postings almost every
term appears in at least one senior listing, so a maximum saturates to
`advanced` and stops carrying information.

The pool also keeps the full `levels` distribution behind that mode, because the
mode is the right answer for a `job_skills` row and the wrong input to the
ontology, which aggregates a second time. See stage 4.

### 3. Match — `skills/job_matching.py`

Runs each pooled term through `SkillMatcher` once, unchanged from the syllabus
pipeline — the only difference is `domain="job_posting"`, which reframes the LLM
prompt without altering its rules or schema.

Matching each unique term once and fanning the answer back across postings is
the whole point of pooling: matching per posting would re-decide "Kubernetes"
two hundred times and reach different answers on some of them.

The run checkpoints every 50 terms and resumes, which also makes the cutoff
cheap to lower later — dropping `min_df` from 10 to 5 re-matches only the terms
the higher cutoff excluded.

### 4. Aggregate — `skills/ontology.py`

For each career path and each **accepted** match:

```
coverage       = |postings asking for the skill| / postings in the path
required_score = coverage × 100
required_level = the depth at least half of those postings asked for
```

`required_level` is the **weighted median**, and getting there took two attempts.
A maximum was rejected before this was written. A mode replaced it and failed the
same way, more quietly: `advanced` is the largest single bucket corpus-wide, so it
takes the plurality for nearly every skill even where most postings ask for less.
Compounding that with the per-term mode above produced this:

| | beginner | intermediate | advanced |
|---|---|---|---|
| what postings actually asked | 9% | 40% | 51% |
| after the per-term mode | 2% | 33% | 65% |
| after a second mode here | 0.5% | 16% | **83%** |
| weighted median, on the real distribution | 0.5% | 40% | **59%** |

Five requirements in six reading `advanced` is not a demanding market, it is a
statistic that has stopped measuring anything — and it lands on the bar the gap
analysis classifies against, so it made every student look further behind than
they were. The median asks "what depth satisfies half the market", which is what
a requirement means.

A requirement is a fraction, never a count, because the paths are different
sizes — Data Science has 337 postings and AI/ML has 158. Kubernetes in 3 of 3
Backend postings is a bigger requirement than in 30 of 300 DevOps ones, and only
coverage says so.

The numerator is a **union of postings, not a sum of term counts**. Several
terms usually resolve to one skill — `Grafana`, `Prometheus`, `logging`,
`monitoring` and `observability` all become "monitoring and observability" — and
a posting naming three of them is still one posting. Summing counted it three
times and reported the skill at 100% of the DevOps path; the union puts it at
its true 51.5% (136 of 264). The inflation was roughly 2x on the worst cases,
and it landed squarely on the number the gap analysis subtracts against, so the
pool carries posting ids rather than counts to make the union possible.

Only confidently matched terms count. A term the matcher sent to review is not
evidence of a requirement, and letting one through would write a guess into the
knowledge base that every downstream module then treats as ground truth.

## The subtle failure: bare category nouns

The most instructive defect found while building this. Terms like `development`,
`automation`, `security` and `performance` are frequent, grammatically noun
phrases, and retrieve *something* from any taxonomy:

| Term | Confidently resolved to | |
|---|---|---|
| `development` | REST API development | wrong — far too specific |
| `automation` | test automation | wrong — DevOps automation is not test automation |

They are dangerous rather than merely useless: being frequent, they outrank the
real skills they displace, and a wrong canonical id is invisible once stored.
They are filtered by name in `JOB_NOISE_TERMS`, and **any new corpus should be
re-checked for the same pattern** — the specific words will differ.

## Taxonomy integrity

Merging two records for one skill retires the loser's id, but rows already
written still carry it. Left alone the two sides of the join drift apart
silently: a course matched to `custom:java` and a posting matched to
`esco:19a8293b…` describe the same skill and compare as different ones — so the
gap analysis reports a student lacks something they were taught.

This was live in the database and is now repaired by
`db.skills.remap_retired_skills`, which resolves each retired label through the
current alias index and repoints the stored rows. `--db` runs it automatically.

## Running it

```bash
# Mine and pool only — seconds, no model, shows what each cutoff costs
python -m careercompass.cli.extract_job_skills --pool-only

# Smoke test before committing to the full run
python -m careercompass.cli.extract_job_skills --min-df 100 --llm

# The real thing
python -m careercompass.cli.extract_job_skills --llm --db

# Continue an interrupted run
python -m careercompass.cli.extract_job_skills --llm --db --resume
```

| Output | Contents |
|---|---|
| `data/extracted/jobs/term_pool.json` | every term, unfiltered, so the cutoff can be re-tuned without re-mining |
| `data/extracted/jobs/term_matches.json` | the term → taxonomy decision map, and the resume checkpoint |
| `data/extracted/jobs/career_path_skills.json` | the ontology |
| `job_skills` | one row per (posting, term), unresolved ones included |
| `career_path_skills` | the ontology, keyed on path **name** — the two services do not share a database |

## Tests

```bash
python -m tests.test_job_extractor   # sections, boilerplate, refinement, levels
python -m tests.test_job_corpus      # pooling, the cutoff, ontology arithmetic
```
