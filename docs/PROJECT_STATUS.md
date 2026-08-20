# CareerCompass Implementation Status

Where the code stands against the Knowledge Base and six AI modules of
Section 5.3 of the project report.

**Last updated:** 20 August 2026

Cross-cutting engineering facts — the identity defects, silent-failure modes,
measured numbers, hardware constraints and open decisions — are in
[ENGINEERING_NOTES.md](ENGINEERING_NOTES.md). This page is only the build state.

**Legend:** ✅ built · 🟡 partial · ❌ not started

## Modules

| Piece | Status |
|---|---|
| M1 Transcript analysis | ✅ `parsing/transcript.py` + `parsing/grades.py`, exposed at `POST /api/v1/transcripts/parse` |
| **M2 Skill vector** | ✅ `skills/vector.py` — deterministic, quiz override, 39 tests |
| M3 Skill gap + dashboard | ❌ Not started — unblocked; add `skill_type` to `career_path_skills` first |
| M4 Course recommendation | ❌ Behind M3 |
| M5 Quiz | ❌ Behind M3 |
| M6 Job & mentor matching | ❌ Behind M3 |
| FastAPI layer | ✅ 15 endpoints across extraction, results, matching, review, transcript, health |

## Knowledge base

| Piece | Status |
|---|---|
| Course → skill map | 🟡 10 of 114 courses from real syllabi; 20 PDFs collected |
| Course → skill map (synthetic) | ✅ 96 courses under `data/mock/` — testing only, never production |
| Job catalog | ✅ 2,238 postings across 9 career paths, skills extracted and matched |
| Career-path → required-skills ontology | ✅ 771 requirements, 82–105 per path |
| Skills taxonomy | ✅ 903 rows, 0 orphans |
| Online course catalog (Coursera/Udemy) | ❌ Not started |
| Mentor catalog | ❌ Not started |

## The critical path

Course coverage is the constraint. The ontology describes all nine career
paths; the student side has real syllabi for 10 of 114 courses.

`data/plans/required_syllabi.md` tracks the collection across all four majors
and regenerates from disk:

```bash
python -m careercompass.cli.build_syllabus_list
```

Synthetic course → skill rows fill the gap so M2 and M3 can be built and
verified now. They must never reach the production `course_skills` table — see
ENGINEERING_NOTES §10.

## Next

1. **Commit.** Three sessions of work are uncommitted, including a `.gitignore`
   fix that stops student personal data reaching the repository.
2. **Decide the canonical course id** before more syllabi are extracted;
   retrofitting means re-extracting everything. ENGINEERING_NOTES §3.
3. **Add `skill_type` to `career_path_skills`**, then build M3.
4. **Collect the remaining real syllabi** — the long pole, and dependent on
   other people.
5. **Tell the backend owner about the contract mismatch.** Five of his six
   endpoints do not exist. ENGINEERING_NOTES §12b.

## Interfaces

| Document | Covers |
|---|---|
| [ENGINEERING_NOTES.md](ENGINEERING_NOTES.md) | how the system actually behaves, and why |
| [API_DESIGN.md](API_DESIGN.md) | platform-wide interface: five actors, all six modules |
| [SKILL_EXTRACTION_API.md](SKILL_EXTRACTION_API.md) | the skills subsystem, as implemented |
| [SYLLABUS_SKILL_EXTRACTION.md](SYLLABUS_SKILL_EXTRACTION.md) | syllabus pipeline internals |
| [JOB_SKILL_EXTRACTION.md](JOB_SKILL_EXTRACTION.md) | job pipeline internals |
