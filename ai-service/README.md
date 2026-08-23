# CareerCompass AI Service

The Python service parses transcripts and syllabi, maintains the canonical
skill vocabulary, calculates skill vectors and gaps, recommends courses,
generates quizzes, and performs matching operations.

## Requirements

- Python 3.10+
- `uv` or `pip`
- PostgreSQL for database-backed features

## Install

```bash
cd ai-service
uv venv .venv
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
```

Optional semantic and hosted-LLM dependencies:

```bash
uv pip install -e ".[semantic]"
uv pip install -e ".[llm]"
```

## Run the API

```bash
cd ai-service
uvicorn careercompass.api.app:app --reload --port 8000
```

## Useful commands

```bash
cc-build-taxonomy
cc-extract-skills "data/syllabi/robotics_programming.pdf" --match
cc-match-skills "data/syllabi/robotics_programming.pdf"
cc-parse-transcript plan.pdf
```

## Test

```bash
cd ai-service
for test_file in tests/test_*.py; do
  python "$test_file" || exit 1
done
```

Implementation and API notes are in [`docs/`](docs/).
