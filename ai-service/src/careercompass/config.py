"""
CareerCompass — Shared Configuration

Two things every part of the project needs and none of them should own:
where the data lives, and how to reach the database.

Paths are resolved from this file's location rather than the working
directory. That is the point of the module: before it existed, every
path was written as `Path("src/data/...")`, so the whole project only
worked when it happened to be launched from the repository root.

Set CC_DATA_DIR to move the data tree somewhere else — a shared volume,
a scratch disk, a per-developer directory.

Usage:
    from careercompass.config import DB_CONFIG, TAXONOMY_DIR
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # loads .env from the working directory or any parent

# ── Layout ─────────────────────────────────────────────────────

# src/careercompass/config.py → src/careercompass → src → repository root
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent

DATA_DIR = Path(os.getenv("CC_DATA_DIR") or REPO_ROOT / "data")

# Scraper input and output
RAW_DATA_DIR = DATA_DIR / "raw"
CLEAN_DATA_DIR = DATA_DIR / "clean"

# Parser and extractor output
EXTRACTED_DIR = DATA_DIR / "extracted"
SYLLABI_DIR = EXTRACTED_DIR / "syllabi"
SKILLS_DIR = EXTRACTED_DIR / "skills"
JOBS_DIR = EXTRACTED_DIR / "jobs"
TEMP_DIR = DATA_DIR / "temp"

# Synthetic course→skill maps, for demonstrating the product against a corpus wider than the
# syllabi that have actually been extracted. Off unless explicitly asked for, and never merged
# into SKILLS_DIR: every file in there says "Not a real MEU document", and a system that cannot
# repeat that claim is one that quietly presents invented coursework as real.
MOCK_SKILLS_DIR = DATA_DIR / "mock" / "skills"
INCLUDE_MOCK_COURSES = os.getenv("CC_INCLUDE_MOCK_COURSES", "0") == "1"

# Hand-maintained lookups that are reviewed rather than derived. Kept out of the code so the
# person who names a study field can correct its mapping without a release.
MAPPING_DIR = DATA_DIR / "mapping"
STUDY_FIELD_CAREER_PATHS_PATH = MAPPING_DIR / "study_field_career_paths.json"

# Canonical vocabulary: one source file, three build artifacts
TAXONOMY_DIR = DATA_DIR / "taxonomy"
CUSTOM_SKILLS_PATH = TAXONOMY_DIR / "custom_skills.json"
TAXONOMY_CACHE_DIR = TAXONOMY_DIR / "cache"
TAXONOMY_PATH = TAXONOMY_DIR / "taxonomy.jsonl"
VECTOR_INDEX_PATH = TAXONOMY_DIR / "vector_index.npz"

# ── PostgreSQL ─────────────────────────────────────────────────
# Lives here rather than in jobs/config.py, where it used to sit: the
# skills pipeline needs a connection too, and reaching into the scraper
# package for one inverted the dependency between them.
DB_CONFIG = {
    "host": os.getenv("CC_DB_HOST"),
    "port": int(os.getenv("CC_DB_PORT", "5432")),
    "dbname": os.getenv("CC_DB_NAME"),
    "user": os.getenv("CC_DB_USER"),
    "password": os.getenv("CC_DB_PASSWORD"),
    "connect_timeout": max(1, int(os.getenv("CC_DB_CONNECT_TIMEOUT", "5"))),
    "application_name": "careercompass-ai",
}
