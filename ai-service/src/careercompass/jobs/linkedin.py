"""
CareerCompass — LinkedIn Job Scraper

Scrapes job listings from LinkedIn's public guest API and stores them
in PostgreSQL.

Handles:
  - location targeting (Amman, Jordan)
  - Blog/noise filtering
  - Deduplication by URL
  - Rotating User-Agent headers
  - Retry logic with exponential backoff
  - Randomized delays to avoid IP bans
  - Structured logging
  - Saves to both JSON (raw backup) and PostgreSQL
  - Resume capability (skips already-scraped URLs)
  - Extracts structured detail fields (seniority, type, etc.)

"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from careercompass.jobs.config import (
    CAREER_PATH_QUERIES,
    CLEAN_DATA_DIR,
    PAGES_PER_QUERY,
    RAW_DATA_DIR,
    TARGET_LOCATIONS,
)
from careercompass.db.connection import get_connection
from careercompass.db.jobs import get_existing_urls, init_job_tables, insert_jobs
from careercompass.jobs.utils import (
    clean_text,
    is_noise,
    make_request,
    random_delay,
    slugify,
)

# ── Logging Setup ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("careercompass.scraper")

# LinkedIn guest endpoint (no login required)
SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)


# ── Job Detail Scraper ─────────────────────────────────────────
def get_job_details(job_url: str) -> dict:
    """
    Fetch a single LinkedIn job page and extract detailed fields:
      - Full description text
      - Seniority level, employment type, job function, industries
      - Posted date
    """
    resp = make_request(job_url)
    if resp is None:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    details = {}

    # ── Description ──
    desc_div = soup.find("div", class_="show-more-less-html__markup")
    if desc_div:
        details["description"] = desc_div.get_text("\n", strip=True)

    # ── Posted date ──
    date_el = soup.find("span", class_="posted-time-ago__text")
    if not date_el:
        date_el = soup.find("span", class_="posted-time-ago")
    if date_el:
        details["posted_date"] = date_el.get_text(strip=True)

    # ── Structured criteria (seniority, type, function, industries) ──
    # LinkedIn renders these as a list of <li> items inside a criteria section.
    criteria_items = soup.find_all(
        "li", class_="description__job-criteria-item"
    )
    criteria_map = {
        "Seniority level": "seniority_level",
        "Employment type": "employment_type",
        "Job function": "job_function",
        "Industries": "industries",
    }
    for item in criteria_items:
        header_el = item.find("h3", class_="description__job-criteria-subheader")
        value_el = item.find("span", class_="description__job-criteria-text")
        if header_el and value_el:
            header_text = header_el.get_text(strip=True)
            field_key = criteria_map.get(header_text)
            if field_key:
                details[field_key] = value_el.get_text(strip=True)

    return details


# ── Search Page Scraper ────────────────────────────────────────
def scrape_search_page(
    keyword: str,
    location: str,
    career_path: str,
    page: int,
    seen_urls: set,
) -> list[dict]:
    """
    Scrape a single page of LinkedIn search results.
    Returns a list of job dicts, filtering out noise and duplicates.
    """
    start_index = page * 25
    params = {
        "keywords": keyword,
        "location": location,
        "start": start_index,
    }

    resp = make_request(SEARCH_URL, params=params)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("li")
    jobs = []

    for card in cards:
        try:
            title_el = card.find("h3", class_="base-search-card__title")
            if not title_el:
                continue  # not a real job card

            title = clean_text(title_el.text)

            # ── Noise filter ──
            if is_noise(title):
                logger.debug("Skipped noise: %s", title[:60])
                continue

            company_el = card.find("h4", class_="base-search-card__subtitle")
            location_el = card.find("span", class_="job-search-card__location")
            link_el = card.find("a", class_="base-card__full-link")

            raw_url = link_el.get("href", "") if link_el else ""
            clean_url = raw_url.split("?")[0] if raw_url else None

            if not clean_url:
                continue

            # ── Deduplication ──
            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            # ── Fetch full details (with delay) ──
            random_delay()
            details = get_job_details(clean_url)

            job = {
                "career_path": career_path,
                "search_query": keyword,
                "title": title,
                "company_name": (
                    clean_text(company_el.text) if company_el else None
                ),
                "location": (
                    clean_text(location_el.text) if location_el else None
                ),
                "url": clean_url,
                "description": details.get("description"),
                "seniority_level": details.get("seniority_level"),
                "employment_type": details.get("employment_type"),
                "job_function": details.get("job_function"),
                "industries": details.get("industries"),
                "posted_date": details.get("posted_date"),
                "is_relevant": True,
            }

            jobs.append(job)

        except Exception as e:
            logger.debug("Failed to parse card: %s", e)
            continue

    return jobs


# ── Main Scraper Orchestrator ──────────────────────────────────
def run_scraper(
    career_paths: dict | None = None,
    locations: list[str] | None = None,
    pages: int = PAGES_PER_QUERY,
    dry_run: bool = False,
):
    """
    Main entry point. Scrapes LinkedIn for each career path × query × location.

    Args:
        career_paths: dict of {career_path: [queries]}. Defaults to config.
        locations: list of locations. Defaults to config.
        pages: number of pages per query (25 jobs/page).
        dry_run: if True, save JSON only — don't write to PostgreSQL.
    """
    career_paths = career_paths or CAREER_PATH_QUERIES
    locations = locations or TARGET_LOCATIONS

    # ── Ensure output dirs exist ──
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    os.makedirs(CLEAN_DATA_DIR, exist_ok=True)

    # ── Database setup ──
    conn = None
    seen_urls = set()

    if not dry_run:
        try:
            init_job_tables()
            conn = get_connection()
            seen_urls = get_existing_urls(conn)
            logger.info(
                "Connected to PostgreSQL. %d existing jobs in DB.", len(seen_urls)
            )
        except Exception as e:
            logger.warning(
                "PostgreSQL unavailable (%s). Falling back to JSON-only mode.", e
            )
            dry_run = True

    all_jobs = []
    stats = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "career_paths": {},
    }

    total_paths = len(career_paths)
    for path_idx, (career_path, queries) in enumerate(career_paths.items(), 1):
        path_jobs = []
        logger.info(
            "━━━ [%d/%d] Career Path: %s ━━━", path_idx, total_paths, career_path
        )

        for query in queries:
            for location in locations:
                logger.info(
                    "  🔍 Query: '%s' in '%s' (%d pages)",
                    query, location, pages,
                )

                for page in range(pages):
                    page_jobs = scrape_search_page(
                        keyword=query,
                        location=location,
                        career_path=career_path,
                        page=page,
                        seen_urls=seen_urls,
                    )

                    if not page_jobs:
                        logger.info("    Page %d: empty — stopping.", page + 1)
                        break

                    path_jobs.extend(page_jobs)
                    logger.info(
                        "    Page %d: +%d jobs (total: %d)",
                        page + 1, len(page_jobs), len(path_jobs),
                    )

                    random_delay()

        # ── Save raw JSON per career path ──
        slug = slugify(career_path)
        raw_path = os.path.join(RAW_DATA_DIR, f"{slug}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(path_jobs, f, indent=2, ensure_ascii=False)
        logger.info(
            "  💾 Saved %d raw jobs → %s", len(path_jobs), raw_path
        )

        # ── Insert into PostgreSQL ──
        if conn and not dry_run and path_jobs:
            try:
                inserted = insert_jobs(conn, path_jobs)
                logger.info("  🗄️  Inserted %d new jobs into PostgreSQL.", inserted)
            except Exception as e:
                logger.error("  DB insert failed: %s", e)

        all_jobs.extend(path_jobs)
        stats["career_paths"][career_path] = len(path_jobs)

    # ── Save combined master file ──
    master_path = os.path.join(CLEAN_DATA_DIR, "all_jobs.json")
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    # ── Stats ──
    stats["finished_at"] = datetime.now(timezone.utc).isoformat()
    stats["total_jobs"] = len(all_jobs)

    stats_path = os.path.join(RAW_DATA_DIR, "scrape_report.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    # ── Summary ──
    logger.info("═══════════════════════════════════════════════")
    logger.info("  Scraping Complete!")
    logger.info("  Total jobs collected: %d", len(all_jobs))
    for cp, count in stats["career_paths"].items():
        logger.info("    %-30s %d jobs", cp, count)
    logger.info("  Raw JSON:    %s", RAW_DATA_DIR)
    logger.info("  Master JSON: %s", master_path)
    if conn:
        logger.info("  PostgreSQL:  ✅ saved")
    logger.info("═══════════════════════════════════════════════")

    if conn:
        conn.close()

    return all_jobs


# ── CLI Entry Point ────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="CareerCompass — LinkedIn Job Scraper"
    )
    parser.add_argument(
        "--career-path",
        type=str,
        default=None,
        help="Scrape only a specific career path (e.g., 'Cybersecurity')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        help="Scrape only a specific location (e.g., 'Amman, Jordan')",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=PAGES_PER_QUERY,
        help=f"Pages per query (default: {PAGES_PER_QUERY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Save to JSON only — don't write to PostgreSQL",
    )
    args = parser.parse_args()

    # Filter career paths if specified
    paths = CAREER_PATH_QUERIES
    if args.career_path:
        matched = {
            k: v for k, v in paths.items()
            if args.career_path.lower() in k.lower()
        }
        if not matched:
            logger.error(
                "Career path '%s' not found. Available: %s",
                args.career_path, ", ".join(paths.keys()),
            )
            sys.exit(1)
        paths = matched

    locations = TARGET_LOCATIONS
    if args.location:
        locations = [args.location]

    run_scraper(
        career_paths=paths,
        locations=locations,
        pages=args.pages,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
