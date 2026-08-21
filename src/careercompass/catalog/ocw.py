"""
MIT Learn catalog ingestion — OpenCourseWare, xPRO and MITx in one API.

`api.learn.mit.edu` is public, unauthenticated, and carries 3,002 courses. It
is the easiest of the three sources licence-wise: every record states
`license_cc`, so Creative Commons material is identifiable rather than assumed.

The same rule still applies as elsewhere — descriptions are read by the matcher
and dropped — because the feed mixes CC-licensed OCW material with xPRO and
MITx courses that are not CC. Storing only what is uniformly safe is simpler
than storing per-record rights and hoping every later reader checks them.
"""

import logging

from careercompass.catalog.base import Course, infer_level, normalise
from careercompass.jobs.utils import clean_text, make_request, random_delay

logger = logging.getLogger(__name__)

API_URL = "https://api.learn.mit.edu/api/v1/courses/"
JSON_HEADERS = {"Accept": "application/json"}
PLATFORM = "ocw"
PAGE_SIZE = 100


def _weeks_to_hours(record: dict) -> float | None:
    """Approximate contact hours from the weekly commitment the API reports."""
    weeks = record.get("max_weeks") or record.get("min_weeks")
    hours = record.get("max_weekly_hours") or record.get("min_weekly_hours")
    try:
        if weeks and hours:
            return round(float(weeks) * float(hours), 1)
    except (TypeError, ValueError):
        pass
    return None


def _to_course(record: dict) -> Course | None:
    title = clean_text(record.get("title") or "")
    url = (record.get("url") or "").strip()
    if not title or not url:
        return None

    # full_description is longer and gives the matcher more to work with;
    # description is the fallback. Both arrive as HTML, which clean_text strips.
    body = record.get("full_description") or record.get("description") or ""
    languages = record.get("languages") or []
    sub_platform = (record.get("platform") or {}).get("code")

    return Course(
        course_id=f"{PLATFORM}:{record.get('readable_id') or record.get('id')}",
        platform=PLATFORM,
        title=title,
        url=url,
        description=clean_text(body),
        level=infer_level(title),
        language=languages[0] if languages else None,
        duration_hours=_weeks_to_hours(record),
        rating=None,
        extra={
            "sub_platform": sub_platform,
            "license_cc": bool(record.get("license_cc")),
            "free": bool(record.get("free")),
            "certification": bool(record.get("certification")),
        },
    )


def fetch(limit: int = None, *, page_size: int = PAGE_SIZE, polite: bool = True,
          cc_only: bool = False) -> list:
    """
    Page through the MIT Learn catalog.

    Args:
        limit: stop after roughly this many courses. None fetches everything.
        page_size: courses per request.
        polite: pause between requests.
        cc_only: keep only Creative Commons licensed records. Off by default —
            the whole feed is fine to *index*; the flag exists for anyone who
            later wants to display more than a title and a link.
    """
    courses = []
    url, params = API_URL, {"limit": page_size, "offset": 0}

    while True:
        response = make_request(url, params=params, headers=JSON_HEADERS)
        if response is None:
            logger.warning("ocw: giving up with %d courses", len(courses))
            break
        try:
            payload = response.json()
        except ValueError:
            logger.warning("ocw: unparsable response")
            break

        results = payload.get("results") or []
        if not results:
            break

        for record in results:
            course = _to_course(record)
            if course is None:
                continue
            if cc_only and not course.extra.get("license_cc"):
                continue
            courses.append(course)

        if limit and len(courses) >= limit:
            courses = courses[:limit]
            break

        nxt = payload.get("next")
        if not nxt:
            break
        # `next` is absolute and already carries the offset, so params must go.
        url, params = nxt.replace("http://", "https://"), None

        if polite:
            random_delay()

    logger.info("ocw: fetched %d courses", len(courses))
    return normalise(courses)
