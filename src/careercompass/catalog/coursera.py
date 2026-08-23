"""
Coursera catalog ingestion via the public `courses.v1` API.

No scraping and no API key: the endpoint is publicly readable and returns
23,564 courses as of August 2026. Two things about it are worth knowing before
relying on it.

**It is documented as beta and free to break compatibility without warning.**
The fetch is therefore defensive about missing fields, and the pull is cached
so a mid-run change cannot destroy work already done.

**The catalog copyright belongs to Coursera's university partners, and the API
grants no licence to republish descriptions.** Descriptions are read by the
matcher and dropped; only derived skill ids, the title and the URL are stored,
and the product links out rather than reproducing partner text.

The `q=search` finder documented in some places is not implemented on the live
endpoint — it answers `Routing error: finder 'search' not implemented`. The
whole catalog is paginated instead and filtered locally, which is also the only
way to build a stable index rather than one shaped by query terms.
"""

import logging

from careercompass.catalog.base import Course, infer_level, normalise
from careercompass.jobs.utils import clean_text, make_request, random_delay

logger = logging.getLogger(__name__)

API_URL = "https://api.coursera.org/api/courses.v1"
JSON_HEADERS = {"Accept": "application/json"}
COURSE_URL = "https://www.coursera.org/learn/{slug}"
PLATFORM = "coursera"

# The API accepts larger, but a page this size keeps one failed request cheap
# to retry and the whole catalog is still only ~120 requests.
PAGE_SIZE = 200
FIELDS = "slug,description,name,workload,primaryLanguages"


def _to_course(element: dict) -> Course | None:
    slug = (element.get("slug") or "").strip()
    name = clean_text(element.get("name") or "")
    if not slug or not name:
        return None

    languages = element.get("primaryLanguages") or []
    return Course(
        course_id=f"{PLATFORM}:{element.get('id') or slug}",
        platform=PLATFORM,
        title=name,
        url=COURSE_URL.format(slug=slug),
        description=clean_text(element.get("description") or ""),
        level=infer_level(name),
        language=languages[0] if languages else None,
        # The public endpoint exposes no rating, so ranking cannot lean on
        # quality signals for this source — see skills/recommend.py.
        rating=None,
        extra={"slug": slug, "workload": element.get("workload")},
    )


def fetch(limit: int = None, *, page_size: int = PAGE_SIZE, polite: bool = True) -> list:
    """
    Page through the catalog.

    Args:
        limit: stop after roughly this many courses. None fetches everything.
        page_size: courses per request.
        polite: pause between requests. Leave on for anything but a tiny probe.

    Returns:
        Normalised ``Course`` records. Never raises on a failed page — it stops
        and returns what it has, so a long pull is not lost to one bad request.
    """
    courses, start, total = [], 0, None

    while True:
        params = {"start": start, "limit": page_size, "fields": FIELDS}
        response = make_request(API_URL, params=params, headers=JSON_HEADERS)
        if response is None:
            logger.warning("coursera: giving up at start=%s with %d courses",
                           start, len(courses))
            break

        try:
            payload = response.json()
        except ValueError:
            logger.warning("coursera: unparsable response at start=%s", start)
            break

        if "elements" not in payload:
            logger.warning("coursera: unexpected response at start=%s: %s",
                           start, str(payload)[:120])
            break

        elements = payload.get("elements") or []
        if not elements:
            break

        for element in elements:
            course = _to_course(element)
            if course is not None:
                courses.append(course)

        paging = payload.get("paging") or {}
        if total is None:
            total = paging.get("total")
            logger.info("coursera: %s courses in the catalog", total)

        if limit and len(courses) >= limit:
            courses = courses[:limit]
            break

        nxt = paging.get("next")
        if not nxt:
            break
        start = int(nxt)

        if polite:
            random_delay()

    logger.info("coursera: fetched %d courses", len(courses))
    return normalise(courses)
