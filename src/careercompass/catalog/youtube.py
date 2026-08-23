"""
YouTube catalog ingestion via the official Data API v3.

Listed as a platform in `API_DESIGN.md` and worth having: for many practical
skills the best free material is a conference talk or a tutorial series, not a
structured course.

Needs `CC_YOUTUBE_API_KEY`. Without one this source is **skipped with a
warning rather than failing the run** — the other two sources produce a usable
catalog on their own, and a missing optional key should not stop a pipeline.

Quota is the real constraint: a `search.list` call costs 100 units against a
10,000-unit daily default, so roughly 100 searches a day. The queries are
therefore driven by taxonomy skill labels rather than sprayed, and results are
cached like every other source.
"""

import logging
import os

from careercompass.catalog.base import Course, infer_level, normalise
from careercompass.jobs.utils import clean_text, make_request, random_delay

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"
PLATFORM = "youtube"
JSON_HEADERS = {"Accept": "application/json"}

# One search costs 100 quota units. 50 is the API maximum per call, so this
# takes the most results possible for the price.
RESULTS_PER_QUERY = 50
# Tutorials and talks, not vlogs. Bare skill names return too much noise.
QUERY_TEMPLATE = "{skill} tutorial course"


def _to_course(item: dict) -> Course | None:
    video_id = ((item.get("id") or {}).get("videoId") or "").strip()
    snippet = item.get("snippet") or {}
    title = clean_text(snippet.get("title") or "")
    if not video_id or not title:
        return None

    return Course(
        course_id=f"{PLATFORM}:{video_id}",
        platform=PLATFORM,
        title=title,
        url=VIDEO_URL.format(video_id=video_id),
        description=clean_text(snippet.get("description") or ""),
        level=infer_level(title),
        language=None,
        duration_hours=None,
        # search.list carries no rating or view count; fetching them costs
        # another call per video, which the quota does not justify.
        rating=None,
        extra={"channel": snippet.get("channelTitle"),
               "published_at": snippet.get("publishedAt")},
    )


def fetch(limit: int = None, *, queries: list = None, api_key: str = None,
          polite: bool = True) -> list:
    """
    Search for tutorial material, one query per skill.

    Args:
        limit: stop after roughly this many videos.
        queries: skill labels to search for. Required — there is no catalog to
            page through, only a search index, so something has to say what to
            look for.
        api_key: defaults to ``CC_YOUTUBE_API_KEY``.
        polite: pause between requests.

    Returns an empty list, not an error, when no key is configured.
    """
    api_key = api_key or os.getenv("CC_YOUTUBE_API_KEY", "")
    if not api_key:
        logger.warning("youtube: CC_YOUTUBE_API_KEY is not set; skipping this source")
        return []
    if not queries:
        logger.warning("youtube: no queries given; skipping this source")
        return []

    courses, seen = [], set()
    for skill in queries:
        params = {
            "key": api_key,
            "part": "snippet",
            "type": "video",
            "maxResults": RESULTS_PER_QUERY,
            "q": QUERY_TEMPLATE.format(skill=skill),
            "relevanceLanguage": "en",
            "videoEmbeddable": "true",
        }
        response = make_request(SEARCH_URL, params=params, headers=JSON_HEADERS)
        if response is None:
            logger.warning("youtube: request failed for %r; stopping", skill)
            break
        try:
            payload = response.json()
        except ValueError:
            logger.warning("youtube: unparsable response for %r", skill)
            continue

        if "error" in payload:
            # Quota exhaustion is expected on a free key and is not a bug.
            reason = (payload["error"].get("errors") or [{}])[0].get("reason", "")
            logger.warning("youtube: API error (%s); stopping", reason or "unknown")
            break

        for item in payload.get("items") or []:
            course = _to_course(item)
            if course is None or course.course_id in seen:
                continue
            seen.add(course.course_id)
            # Which skill the search was for; the matcher still decides what
            # the video actually teaches from its title and description.
            course.extra["query_skill"] = skill
            courses.append(course)

        if limit and len(courses) >= limit:
            courses = courses[:limit]
            break
        if polite:
            random_delay()

    logger.info("youtube: fetched %d videos across %d queries", len(courses), len(queries))
    return normalise(courses)
