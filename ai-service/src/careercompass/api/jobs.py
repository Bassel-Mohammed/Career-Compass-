"""
CareerCompass API — Extraction jobs

Matching a syllabus takes about ninety seconds, so it cannot be done
inside a request. Submissions are queued and drained by a single
background worker.

One worker is not a placeholder for a bigger pool. Ollama serialises
inference, so a second concurrent job would not finish sooner — it would
only make both jobs' latency unpredictable and double the peak memory of
the embedding backend.

Job state is in-process and does not survive a restart. That is an
accepted trade at this scale; swapping in Celery or RQ means replacing
this module, not the routes.
"""

import asyncio
import logging
import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from careercompass.api.errors import Problem
from careercompass.api.runtime import runtime
from careercompass.config import SKILLS_DIR
from careercompass.skills.extractor import extract_skills, save_skills
from careercompass.skills.taxonomy import TAXONOMY_VERSION

logger = logging.getLogger("careercompass.api")

# Terms are matched in chunks so progress advances during the slow stage
# and cancellation has somewhere to land. The encode is batched per chunk
# rather than per course, which costs a little vectorisation efficiency —
# but at 0.09 s/term encode against 2.6 s/term generation, the LLM
# dominates and the trade is not close.
MATCH_CHUNK = 8

MAX_TRACKED_JOBS = 200


class JobCancelled(Exception):
    """Raised inside the worker when a cancellation flag is seen."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ExtractionJob:
    extraction_id: str
    content_sha256: str
    cache_key: str
    filename: str
    syllabus: dict
    use_llm: Optional[bool] = None
    store: bool = True

    status: str = "queued"
    stage: str = "queued"
    terms_total: int = 0
    terms_resolved: int = 0
    degraded: bool = False
    result: Optional[dict] = None
    error: Optional[str] = None
    warnings: list = field(default_factory=list)

    created_at: str = field(default_factory=_now)
    finished_at: Optional[str] = None
    _started: float = field(default_factory=time.perf_counter)
    _elapsed: Optional[float] = None
    cancel_requested: bool = False

    @property
    def course_code(self) -> Optional[str]:
        return self.syllabus.get("course_code")

    @property
    def finished(self) -> bool:
        return self.status in ("succeeded", "failed", "cancelled")

    @property
    def elapsed_seconds(self) -> float:
        """
        Wall time so far, frozen once the job ends.

        Without the freeze a finished job's duration keeps climbing on
        every poll, which makes the number useless for reporting how long
        an extraction actually took.
        """
        if self._elapsed is not None:
            return self._elapsed
        return round(time.perf_counter() - self._started, 2)

    def finish(self, status: str) -> None:
        """Record the terminal state and stop the clock."""
        self.status = status
        self.stage = "done"
        self._elapsed = round(time.perf_counter() - self._started, 2)
        self.finished_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "extraction_id": self.extraction_id,
            "status": self.status,
            "course_code": self.course_code,
            "content_sha256": self.content_sha256,
            "degraded": self.degraded,
            "progress": {
                "stage": self.stage,
                "terms_total": self.terms_total,
                "terms_resolved": self.terms_resolved,
                "elapsed_seconds": self.elapsed_seconds,
            },
            "result": self.result,
            "warnings": self.warnings,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class JobStore:
    """Bounded, insertion-ordered job history keyed by id and by content."""

    def __init__(self, limit: int = MAX_TRACKED_JOBS):
        self._jobs: OrderedDict[str, ExtractionJob] = OrderedDict()
        self._by_cache_key: dict[str, str] = {}
        self._limit = limit

    def add(self, job: ExtractionJob) -> None:
        self._jobs[job.extraction_id] = job
        self._by_cache_key[job.cache_key] = job.extraction_id
        self._evict()

    def get(self, extraction_id: str) -> Optional[ExtractionJob]:
        return self._jobs.get(extraction_id)

    def list(self, limit: int = 20) -> list[ExtractionJob]:
        """Tracked jobs, newest first, so a lost id can be recovered."""
        return list(reversed(self._jobs.values()))[:limit]

    def find_succeeded(self, cache_key: str) -> Optional[ExtractionJob]:
        """A completed job for the same document and taxonomy, if any."""
        extraction_id = self._by_cache_key.get(cache_key)
        job = self._jobs.get(extraction_id) if extraction_id else None
        if job is not None and job.status == "succeeded":
            return job
        return None

    def _evict(self) -> None:
        """Drop the oldest finished jobs; never evict queued or running work."""
        while len(self._jobs) > self._limit:
            for extraction_id, job in self._jobs.items():
                if job.finished:
                    self._jobs.pop(extraction_id)
                    if self._by_cache_key.get(job.cache_key) == extraction_id:
                        self._by_cache_key.pop(job.cache_key, None)
                    break
            else:
                return  # nothing evictable


def cache_key_for(
    content_sha256: str,
    *,
    store: bool = True,
    use_llm: Optional[bool] = None,
) -> str:
    """
    Idempotency key: document content plus the taxonomy it would match against.

    The taxonomy fingerprint belongs in the key because a result is only
    meaningful against the vocabulary that produced it — rebuilding the
    taxonomy must invalidate prior extractions rather than serve stale
    mappings from cache.
    """
    try:
        fingerprint = runtime.require().taxonomy.fingerprint
    except Problem:
        fingerprint = "cold"
    # A proposal-only run and a stored run are not interchangeable.  In
    # particular, serving a cached proposal for a later ``store=true`` request
    # would return success without ever publishing the course map.  The LLM
    # override also changes matching decisions, so it is part of the identity
    # rather than an incidental execution option.
    llm_mode = "default" if use_llm is None else ("on" if use_llm else "off")
    storage_mode = "stored" if store else "proposal"
    return f"{content_sha256}:{fingerprint}:{storage_mode}:llm={llm_mode}"


# ── The worker ─────────────────────────────────────────────────
def _run_job(job: ExtractionJob) -> None:
    """The blocking pipeline. Runs on a worker thread, never on the loop."""
    job.status = "running"

    job.stage = "extracting"
    skills = extract_skills(job.syllabus)
    job.terms_total = len(skills)

    job.stage = "matching"
    matcher = runtime.matcher_for(job.use_llm)
    # Degraded means "the LLM was wanted and could not be reached", not
    # "the LLM is off". A deliberately disabled stage is configuration, and
    # flagging it as degradation would make the field meaningless on every
    # run of a deployment that does not use an LLM at all.
    decider = matcher.decider
    job.degraded = decider.enabled and not decider.available
    if job.degraded:
        job.warnings.append(
            f"LLM stage unavailable ({decider.reason_unavailable}); "
            "ambiguous terms were sent to the review queue instead."
        )

    matches = []
    for start in range(0, len(skills), MATCH_CHUNK):
        if job.cancel_requested:
            raise JobCancelled()
        matches.extend(matcher.match_skills(skills[start:start + MATCH_CHUNK]))
        job.terms_resolved = len(matches)

    matcher.attach(skills, matches)
    summary = matcher.summary(matches)

    extra = {
        "taxonomy_version": TAXONOMY_VERSION,
        "match_summary": {
            "by_status": summary["by_status"],
            "by_method": summary["by_method"],
        },
    }
    course_code = job.course_code
    if job.store:
        job.stage = "storing"
        output_path = SKILLS_DIR / f"{course_code}.json"
        save_skills(course_code, skills, str(output_path), extra=extra)
        try:
            from careercompass.db.skills import store_course_skills
            store_course_skills(course_code, skills)
        except Exception as exc:  # noqa: BLE001
            # The accepted JSON artifact is already written, so a database outage
            # degrades the job rather than failing it.
            logger.warning("Database write failed for %s: %s", course_code, exc)
            job.warnings.append(f"Results saved to disk but not to the database: {exc}")

    job.result = {
        "course_code": course_code,
        "total_skills": len(skills),
        **extra,
        "skills": skills,
    }
    job.stage = "done"


class ExtractionQueue:
    """A FIFO of pending jobs drained by one background task."""

    def __init__(self, store: JobStore, maxsize: int = 32):
        self.store = store
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._task: Optional[asyncio.Task] = None
        self._maxsize = maxsize

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._drain(), name="extraction-worker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def submit(self, job: ExtractionJob) -> None:
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            raise Problem.queue_full(self._maxsize) from None
        self.store.add(job)

    async def _drain(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job.cancel_requested:
                    job.finish("cancelled")
                else:
                    await asyncio.to_thread(_run_job, job)
                    job.finish("succeeded")
            except JobCancelled:
                job.result = None
                job.finish("cancelled")
                logger.info("Extraction %s cancelled", job.extraction_id)
            except Exception as exc:  # noqa: BLE001
                job.error = f"{type(exc).__name__}: {exc}"
                job.finish("failed")
                logger.exception("Extraction %s failed", job.extraction_id)
            finally:
                self._queue.task_done()


def new_job_id() -> str:
    return f"ext_{uuid.uuid4().hex[:12]}"


def queue_size() -> int:
    try:
        return max(1, int(os.getenv("CC_API_QUEUE_SIZE", "32")))
    except ValueError:
        return 32
