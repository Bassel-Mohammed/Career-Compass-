<<<<<<< HEAD
# CareerCompass Backend

Backend for **CareerCompass** — "AI-powered Skills Enhancement and Job Matching System"
(MEU Graduation Project, Basil Mohammad & Mohammed Al-Madhoun, supervised by Dr. Shadi Ettantawi).

Built with **Java 17 + Spring Boot 3**, implementing the Container-level "Backend" component
described in the project report (Section 5.1), organised into:

```
Security Layer -> Business Layer -> Integration Layer -> Data Access Layer
```

The **Data Analyses Layer** (NLP, embeddings, skill-vector computation) is a *separate* Python/FastAPI
service developed independently and consumed via REST through the Integration Layer.

## Running locally (dev profile, H2 in-memory DB)

```bash
mvn spring-boot:run
```

- API base URL: `http://localhost:8080`
- Swagger UI: `http://localhost:8080/swagger-ui.html`
- H2 console: `http://localhost:8080/h2-console` (JDBC URL: `jdbc:h2:mem:careercompass`)

## Profiles

| Profile | Database | Notes |
|---|---|---|
| `dev` (default) | H2 in-memory | Fast local development/testing |
| `prod` | MySQL | Requires `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` env vars |

## Documentation

Increment-by-increment build documentation lives in [`docs/`](./docs), one file per development
increment, describing what was built, key decisions, and open items.
=======
# CareerCompass

Finds the gap between what a university course teaches and what the job
market asks for.

Course syllabi and job postings describe the same skills in different
words — a syllabus says "GazeboSim Harmonic", a posting says "Gazebo
simulator". CareerCompass parses both, resolves each phrase onto one
canonical skill vocabulary, and compares them.

## Install

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e .

cp .env.example .env      # then fill in the PostgreSQL credentials
```

Optional semantic models and the hosted Anthropic alternative:

```bash
uv pip install -e ".[semantic]"  # BAAI/bge-m3 retrieval and reranking
uv pip install -e ".[llm]"       # only for the optional Anthropic provider
```

The recommended local LLM needs no Python SDK:

```bash
ollama pull qwen3:8b
```

## Use

```bash
# Build the canonical skill vocabulary (once)
cc-build-taxonomy                          # curated technology skills
cc-build-taxonomy --esco --esco-limit 3000 # plus ESCO (cached, resumable)

# Syllabus → skills → canonical ids
cc-extract-skills "tests/fixtures/robotics_programming.pdf" --match
cc-match-skills   "tests/fixtures/robotics_programming.pdf" # full match report

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

- [CareerCompass skill extraction and matching guide](docs/SYLLABUS_SKILL_EXTRACTION.md)
>>>>>>> origin/mohammed
