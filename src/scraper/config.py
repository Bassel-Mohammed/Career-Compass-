"""
CareerCompass LinkedIn Scraper — Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root

# ── PostgreSQL Connection ──────────────────────────────────────
DB_CONFIG = {
    "host": os.getenv("CC_DB_HOST"),
    "port": int(os.getenv("CC_DB_PORT", "5432")),
    "dbname": os.getenv("CC_DB_NAME"),
    "user": os.getenv("CC_DB_USER"),
    "password": os.getenv("CC_DB_PASSWORD")
}

# ── Career Path → Search Queries ───────────────────────────────
# Each career path maps to multiple LinkedIn search keywords
# to maximize coverage and relevance.
CAREER_PATH_QUERIES = {
    "Full Stack Development": [
        "Full Stack Developer",
        "Full Stack Engineer",
        "MERN Stack Developer",
        "Web Developer Full Stack",
    ],
    "Cybersecurity": [
        "Cybersecurity Analyst",
        "Security Engineer",
        "Information Security Specialist",
        "SOC Analyst",
    ],
    "DevOps & Cloud": [
        "DevOps Engineer",
        "Cloud Engineer",
        "Site Reliability Engineer",
        "Platform Engineer",
    ],
    "Data Science & Analytics": [
        "Data Analyst",
        "Data Scientist",
        "Business Intelligence Analyst",
        "Data Engineer",
    ],
    "Backend Development": [
        "Backend Developer",
        "Backend Engineer",
        "Java Developer",
        "Python Developer",
    ],
    "Mobile Development": [
        "Mobile Developer",
        "Android Developer",
        "iOS Developer",
        "Flutter Developer",
    ],
    "AI & Machine Learning": [
        "Machine Learning Engineer",
        "AI Engineer",
        "NLP Engineer",
        "Deep Learning Engineer",
    ],
    "UI/UX Design": [
        "UI UX Designer",
        "Product Designer",
        "UX Researcher",
        "Interaction Designer",
    ],
    "QA & Testing": [
        "QA Engineer",
        "Test Automation Engineer",
        "Software Tester",
        "Quality Assurance Analyst",
    ],
}

# ── Target Locations ───────────────────────────────────────────
# We use specific cities to target the correct countries.
TARGET_LOCATIONS = [
    "Amman, Jordan",
    "Dubai, United Arab Emirates",
    "Riyadh, Saudi Arabia",
    "Remote",
]

# ── Scraping Settings ──────────────────────────────────────────
PAGES_PER_QUERY = 3          # 25 jobs per page → up to 75 per query
MIN_DELAY = 2.0              # Minimum seconds between requests
MAX_DELAY = 5.0              # Maximum seconds between requests
MAX_RETRIES = 3              # Retry count on failure
REQUEST_TIMEOUT = 15         # Seconds before request times out

# ── User Agents (rotated to reduce fingerprinting) ─────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# ── Output Paths ───────────────────────────────────────────────
RAW_DATA_DIR = os.path.join("src", "data", "raw")
CLEAN_DATA_DIR = os.path.join("src", "data", "clean")

# ── Noise Filter Patterns ──────────────────────────────────────
# Job titles matching these patterns are blog posts, not real jobs.
NOISE_TITLE_PATTERNS = [
    "pros and cons",
    "tips for",
    "how to",
    "what is",
    "vs ",
    " vs.",
    "guide to",
    "best practices",
    "top 10",
    "things you",
    "linkedin profile",
    "career advice",
    "interview tips",
]
