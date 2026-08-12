# CareerCompass

Finds the gap between what a university course teaches and what the job
market asks for.

Course syllabi and job postings describe the same skills in different
words — a syllabus says "GazeboSim Harmonic", a posting says "Gazebo
simulator". CareerCompass parses both, resolves each phrase onto one
canonical skill vocabulary, and compares them.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env      # then fill in the PostgreSQL credentials
```

Optional extras, both off by default:

```bash
pip install -e ".[semantic]"   # BAAI/bge-m3 multilingual retrieval and reranking
pip install -e ".[llm]"        # Claude, for ambiguous taxonomy candidates
```

## Use

```bash
# Build the canonical skill vocabulary (once)
cc-build-taxonomy                          # curated technology skills
cc-build-taxonomy --esco --esco-limit 3000 # plus ESCO (cached, resumable)

# Syllabus → skills → canonical ids
cc-extract-skills "tests/fixtures/Robotics Syl.pdf" --match
cc-match-skills   "tests/fixtures/Robotics Syl.pdf"         # full match report

# Academic plan / transcript
cc-parse-transcript plan.pdf

# API
uvicorn careercompass.api.app:app --reload
```

Every command is also available as `python -m careercompass.cli.<name>`.

## Layout

```
src/careercompass/
  config.py     data paths and database settings
  parsing/      PDF → structured data (transcripts, syllabi, grades)
  skills/       extraction, taxonomy, retrieval, reranking, matching
  jobs/         LinkedIn scraping
  db/           connection, migrations, job and skill persistence
  api/          FastAPI service
  cli/          command-line entry points
data/           raw, clean, extracted, taxonomy
tests/          golden tests, with fixture PDFs
docs/           design notes
```

## Tests

```bash
python -m tests.test_syllabus_parser
python -m tests.test_skill_extractor
python -m tests.test_skill_matcher
```

## Documentation

- [Syllabus skill extraction and RAG taxonomy matching](docs/SYLLABUS_SKILL_EXTRACTION.md)
