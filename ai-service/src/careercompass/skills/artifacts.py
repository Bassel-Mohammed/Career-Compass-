"""
CareerCompass — Artefact loading cache

Every API request used to re-read and re-parse its inputs from disk. The worst
of them, `/api/v1/recommendations`, parsed a 14.2 MB JSON file on **every
call** — 82 ms and 71 MB of transient allocation for a file that changes only
when a batch job rewrites it.

Serially that is survivable. Under load it is not: JSON parsing holds the GIL,
so at 30 concurrent requests p50 went from 15 ms to 3.5 s, a 229x collapse that
has nothing to do with the work being asked for.

**Why a fingerprint and not a timestamp check or a TTL.** These files are
rewritten by batch jobs and by the extraction worker while the server is
running, so a cache that cannot see a change is worse than no cache at all: an
extraction would "succeed" and stay invisible to the API, which is the
silent-failure shape ENGINEERING_NOTES.md §4 is about. Stat-ing costs
microseconds against an 82 ms parse, so the check is effectively free and there
is no window in which the cache is stale.

**Fingerprint every file, never the directory.** Adding a file to a directory
updates the directory's mtime, but *modifying* a file in it does not. A cache
keyed on the directory would miss a re-extracted course. Twenty `stat` calls
cost ~0.1 ms; a wrong answer costs a support ticket.

Usage:
    from careercompass.skills.artifacts import cached_by_files

    @cached_by_files(lambda path: [path])
    def load_index(path=INDEX_PATH) -> dict:
        ...
"""

import functools
import logging
import os
import threading

logger = logging.getLogger("careercompass.artifacts")


def fingerprint(paths) -> tuple:
    """
    A cheap value that changes whenever any of `paths` changes.

    Size as well as mtime, because a file rewritten inside the same mtime tick
    is exactly the case a coarse clock would miss. A path that does not exist
    contributes a marker rather than raising: "absent" is a legitimate state
    that must also invalidate the cache when it stops being true.
    """
    marks = []
    for path in paths:
        try:
            stat = os.stat(path)
            marks.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            marks.append((str(path), None, None))
    return tuple(marks)


def cached_by_files(paths_for):
    """
    Memoise a loader on the fingerprint of the files it reads.

    Args:
        paths_for: called with the loader's own arguments, returns the paths
            whose contents the result depends on.

    The cache holds one entry per (arguments, fingerprint) pair and is cleared
    whenever the fingerprint moves, so it cannot grow with the number of
    rewrites. It is process-local and thread-safe; there is no cross-process
    invalidation and none is needed, because every process fingerprints for
    itself.
    """
    def decorate(loader):
        lock = threading.Lock()
        state = {}

        @functools.wraps(loader)
        def wrapper(*args, **kwargs):
            try:
                key = (args, tuple(sorted(kwargs.items())))
                mark = fingerprint(paths_for(*args, **kwargs))
            except Exception:  # noqa: BLE001 - never fail a request over caching
                logger.debug("fingerprint failed for %s; loading uncached", loader.__name__)
                return loader(*args, **kwargs)

            with lock:
                hit = state.get(key)
                if hit is not None and hit[0] == mark:
                    return hit[1]

            value = loader(*args, **kwargs)
            with lock:
                state[key] = (mark, value)
            return value

        wrapper.cache_clear = state.clear
        return wrapper
    return decorate
