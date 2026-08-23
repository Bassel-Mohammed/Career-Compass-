"""
CareerCompass — course catalog ingestion

One module per source, each returning the same normalised record so nothing
downstream learns where a course came from:

    {course_id, platform, title, url, description,
     level, language, duration_hours, rating}

``description`` is **transient**. It is fetched so the matcher can read it and
is dropped before anything is persisted: Coursera states the catalog copyright
belongs to its university partners and the API grants no licence to republish
descriptions. The recommender links out instead, and the explanation a student
sees is generated from their own skill gap, never copied from a course page.

Udemy is absent deliberately. Its Affiliate API was discontinued on
1 January 2025, leaving no sanctioned programmatic access, and scraping the
site would breach its terms and break against bot protection.
"""

from careercompass.catalog.base import Course, normalise

__all__ = ["Course", "normalise", "get_source", "SOURCES"]

SOURCES = ("coursera", "ocw", "youtube")


def get_source(platform: str):
    """Return a source module's ``fetch(limit, **kwargs)`` callable by name."""
    platform = (platform or "").strip().lower()
    if platform == "coursera":
        from careercompass.catalog import coursera
        return coursera.fetch
    if platform == "ocw":
        from careercompass.catalog import ocw
        return ocw.fetch
    if platform == "youtube":
        from careercompass.catalog import youtube
        return youtube.fetch
    raise ValueError(f"unknown platform {platform!r}; choose from {', '.join(SOURCES)}")
