"""
CareerCompass LinkedIn Scraper — Shared Utilities

Provides:
  - HTTP request wrapper with retry + backoff
  - Rotating User-Agent selection
  - Text cleaning
  - Noise / blog-post detection
"""

import logging
import random
import re
import time

import requests

from careercompass.jobs.config import (
    MAX_RETRIES,
    MIN_DELAY,
    MAX_DELAY,
    NOISE_TITLE_PATTERNS,
    REQUEST_TIMEOUT,
    USER_AGENTS,
)

logger = logging.getLogger("careercompass.scraper")


def get_random_headers() -> dict:
    """Return request headers with a randomly selected User-Agent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }


def make_request(url: str, params: dict = None) -> requests.Response | None:
    """
    GET request with retry logic and exponential backoff.

    Returns the Response on success, or None after all retries fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=get_random_headers(),
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 200:
                return resp

            if resp.status_code == 429:
                wait = 2 ** attempt + random.uniform(1, 3)
                logger.warning(
                    "Rate-limited (429). Waiting %.1fs before retry %d/%d",
                    wait, attempt, MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                logger.warning(
                    "Blocked (403) on attempt %d/%d for %s",
                    attempt, MAX_RETRIES, url[:80],
                )
                time.sleep(2 ** attempt)
                continue

            logger.warning(
                "HTTP %d on attempt %d/%d for %s",
                resp.status_code, attempt, MAX_RETRIES, url[:80],
            )

        except requests.RequestException as exc:
            logger.warning(
                "Request error on attempt %d/%d: %s", attempt, MAX_RETRIES, exc
            )
            time.sleep(2 ** attempt)

    logger.error("All %d retries exhausted for %s", MAX_RETRIES, url[:80])
    return None


def random_delay():
    """Sleep for a random duration between MIN_DELAY and MAX_DELAY."""
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    time.sleep(delay)


def clean_text(text: str) -> str:
    """Strip HTML leftovers, normalize whitespace, and remove unusual unicode characters/control codes."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)       # strip HTML tags
    # Remove Left-to-Right / Right-to-Left marks, Line/Paragraph separators, and zero-width spaces
    text = re.sub(r"[\u200e\u200f\u2028\u2029\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text)            # collapse whitespace
    text = text.strip()
    return text



def is_noise(title: str) -> bool:
    """
    Return True if the title looks like a blog post / sponsored content
    rather than an actual job listing.
    """
    if not title:
        return True
    lower = title.lower()
    return any(pattern in lower for pattern in NOISE_TITLE_PATTERNS)


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug (for filenames)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text
