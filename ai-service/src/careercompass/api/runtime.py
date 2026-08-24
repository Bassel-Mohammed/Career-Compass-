"""
CareerCompass API — Process-wide matcher

The taxonomy, the vector index and the embedder are expensive to
assemble: a cold BGE-M3 index build measured 237 seconds. Building one
per request would put that on every call, so exactly one matcher is built
per process and shared.

Warm-up runs on a background thread so the server starts listening
straight away. `/health/live` answers during the build; `/health/ready`
reports 503 until it finishes. Keeping those two apart is what stops an
orchestrator from killing the container mid-build and restarting the
237-second wait forever.
"""

import logging
import os
import threading
import time

from careercompass.api.errors import Problem
from careercompass.skills.llm import LLMDecider
from careercompass.skills.matcher import SkillMatcher

logger = logging.getLogger("careercompass.api")

COLD = "cold"
WARMING = "warming"
READY = "ready"
FAILED = "failed"


class MatcherRuntime:
    """Lazily built, thread-safe holder for the shared SkillMatcher."""

    def __init__(self):
        self._matcher = None
        self._state = COLD
        self._error = ""
        self._warm_seconds = 0.0
        self._review_revision = 0
        self._lock = threading.Lock()
        # Deciders are cached per override because constructing one probes
        # the provider over HTTP, and per-request overrides are common.
        self._deciders = {}

    # ── State ──────────────────────────────────────────────────
    @property
    def state(self) -> str:
        return self._state

    @property
    def ready(self) -> bool:
        return self._state == READY

    # ── Warm-up ────────────────────────────────────────────────
    def warm(self) -> None:
        """
        Build the matcher. Blocking, idempotent, safe to call from a thread.

        Failures are recorded rather than raised: a broken index should
        surface as an unready instance on /health/ready, not as a crash
        during application start-up.
        """
        with self._lock:
            if self._state in (READY, WARMING):
                return
            self._state = WARMING
            self._error = ""

        started = time.perf_counter()
        try:
            matcher = SkillMatcher.build()
        except Exception as exc:  # noqa: BLE001 - recorded, then reported
            with self._lock:
                self._state = FAILED
                self._error = f"{type(exc).__name__}: {exc}"
            logger.exception("Matcher warm-up failed")
            return

        elapsed = time.perf_counter() - started
        with self._lock:
            self._matcher = matcher
            self._state = READY
            self._warm_seconds = round(elapsed, 2)
        logger.info(
            "Matcher ready in %.1fs (taxonomy %s, %d skills, index %s, llm %s)",
            elapsed, matcher.taxonomy.version, len(matcher.taxonomy),
            matcher.index.backend,
            matcher.decider.display_name if matcher.decider.available else "off",
        )

    def warm_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.warm, name="matcher-warmup", daemon=True)
        thread.start()
        return thread

    # ── Access ─────────────────────────────────────────────────
    def require(self) -> SkillMatcher:
        """The shared matcher, or a 503 explaining why it is not there."""
        if self._state == READY:
            return self._matcher
        if self._state == WARMING:
            raise Problem.matcher_unavailable(
                "The vector index is still being built. A cold build takes "
                "around four minutes; poll /api/v1/health/ready."
            )
        if self._state == FAILED:
            raise Problem.matcher_unavailable(
                f"The matcher failed to build: {self._error}"
            )
        raise Problem.matcher_unavailable("The matcher has not been built yet.")

    def taxonomy_if_ready(self):
        """The loaded taxonomy, or None when the matcher is not built yet.

        Deliberately non-raising, unlike `require`. Callers use this to improve
        a result they can still produce without it — resolving retired skill
        ids — and must not start failing merely because the index is cold.
        """
        return self._matcher.taxonomy if self._state == READY else None

    @property
    def review_revision(self) -> int:
        """Cache key that changes whenever an in-process review is recorded."""
        return self._review_revision

    def overlay_reviewed_matches(self, skills: list) -> int:
        """Overlay the warm matcher's human decisions onto JSON skill rows."""
        with self._lock:
            matcher = self._matcher
        return matcher.overlay_reviewed_matches(skills) if matcher is not None else 0

    def matcher_for(self, use_llm=None) -> SkillMatcher:
        """
        A matcher honouring a per-request LLM override.

        The heavy parts — taxonomy, vector index, reranker — are shared;
        only the decider differs, so an override costs nothing beyond one
        provider probe the first time it is seen.
        """
        base = self.require()
        if use_llm is None:
            return base

        key = bool(use_llm)
        decider = self._deciders.get(key)
        if decider is None:
            decider = LLMDecider(enabled=key)
            self._deciders[key] = decider
            if key and not decider.available:
                logger.warning("LLM override requested but unavailable: %s",
                               decider.reason_unavailable)

        return SkillMatcher(
            base.taxonomy, base.index, base.reranker, decider,
            top_k=base.top_k,
            accept_score=base.accept_score,
            accept_margin=base.accept_margin,
            review_floor=base.review_floor,
            reviewed_matches=base.reviewed_matches,
        )

    def set_reviewed_decision(self, term: str, skill_id, decision: str) -> None:
        """Refresh the warm matcher's review cache after a committed decision."""
        with self._lock:
            if self._matcher is not None:
                self._matcher.set_reviewed_decision(term, skill_id, decision)
                self._review_revision += 1

    # ── Health ─────────────────────────────────────────────────
    def health(self) -> dict:
        """Per-dependency readiness, for /health/ready."""
        checks = {}

        if self._state == READY:
            matcher = self._matcher
            checks["taxonomy"] = {
                "ok": True,
                "version": matcher.taxonomy.version,
                "skills": len(matcher.taxonomy),
            }
            checks["vector_index"] = {
                "ok": True,
                "backend": matcher.index.backend,
                "entries": len(matcher.index),
                "warm_seconds": self._warm_seconds,
            }
            decider = matcher.decider
            checks["llm"] = {
                "ok": decider.available,
                "model": decider.display_name,
            }
            if not decider.available:
                # Not a failure: the matcher degrades to review instead.
                checks["llm"]["reason"] = decider.reason_unavailable
        else:
            unavailable = {"ok": False, "state": self._state}
            if self._error:
                unavailable["reason"] = self._error
            checks["taxonomy"] = dict(unavailable)
            checks["vector_index"] = dict(unavailable)
            checks["llm"] = dict(unavailable)

        checks["database"] = _database_check()
        return checks


# A readiness probe runs on a schedule, not on demand. Opening a PostgreSQL
# connection for each one is churn in exchange for a freshness nobody needs:
# a database that went down two seconds ago is still reported as down on the
# next probe. Short enough that a real outage surfaces immediately in practice.
_DB_PROBE_CACHE = {"at": 0.0, "result": None}
_DB_PROBE_LOCK = threading.Lock()


def _db_probe_ttl() -> float:
    try:
        return max(0.0, float(os.getenv("CC_API_DB_PROBE_TTL", "5")))
    except ValueError:
        return 5.0


def _database_check() -> dict:
    """Probe PostgreSQL without letting a failure propagate, at most every TTL."""
    ttl = _db_probe_ttl()
    if ttl:
        with _DB_PROBE_LOCK:
            cached = _DB_PROBE_CACHE["result"]
            if cached is not None and time.monotonic() - _DB_PROBE_CACHE["at"] < ttl:
                return cached

    result = _probe_database()
    with _DB_PROBE_LOCK:
        _DB_PROBE_CACHE["at"] = time.monotonic()
        _DB_PROBE_CACHE["result"] = result
    return result


def _probe_database() -> dict:
    """One real connection attempt."""
    try:
        from careercompass.db.connection import get_connection
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"driver unavailable: {exc}"}

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc).strip().splitlines()[0][:200]}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def required_ok(checks: dict) -> bool:
    """
    Whether the instance can serve matches.

    The LLM is excluded on purpose. `SkillMatcher.build` degrades when the
    provider is missing — ambiguous terms go to review instead of being
    guessed — so an absent LLM is a quality reduction, not an outage.
    The database is excluded for the same reason: extraction writes to
    disk regardless, and only the review endpoints truly need it.
    """
    return all(checks.get(name, {}).get("ok")
               for name in ("taxonomy", "vector_index"))


# One per process.
runtime = MatcherRuntime()


def warmup_enabled() -> bool:
    return os.getenv("CC_API_WARMUP", "1").strip().lower() not in ("0", "false", "no")
