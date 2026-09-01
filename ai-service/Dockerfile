FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system careercompass \
    && useradd --system --gid careercompass --home-dir /app --shell /usr/sbin/nologin careercompass

WORKDIR /app

# Install the package and its deterministic, non-semantic runtime dependencies.
# Optional model backends are deliberately not part of the development stack.
COPY --chown=careercompass:careercompass pyproject.toml README.md ./
COPY --chown=careercompass:careercompass src ./src
RUN pip install --no-cache-dir .

# Keep the checked-in/local JSON artifacts beside the installed package. The
# compose service points CC_DATA_DIR here because config.py otherwise resolves
# paths relative to site-packages after a non-editable installation.
COPY --chown=careercompass:careercompass data ./data

# These compact build outputs are application data, not optional caches. Failing
# here gives a fresh checkout a useful build error instead of a healthy-looking
# service whose dashboard later rejects every career path.
RUN test -s data/taxonomy/taxonomy.jsonl \
    && test -s data/extracted/jobs/career_path_skills.json \
    && test -n "$(find data/extracted/skills -maxdepth 1 -name '*.json' -print -quit)"

USER careercompass

EXPOSE 8000

CMD ["uvicorn", "careercompass.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
