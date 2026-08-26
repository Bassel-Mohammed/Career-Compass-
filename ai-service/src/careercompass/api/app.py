"""
CareerCompass — FastAPI Backend Service

HTTP interface over the syllabus skill pipeline, specified in
docs/SKILL_EXTRACTION_API.md.

The route layout follows one measurement: parsing and extraction take
about a second, but matching a syllabus takes about ninety. So the fast
deterministic stages are exposed synchronously as a preview, and the slow
semantic stages run as a queued job the client polls. A single endpoint
that blocked for ninety seconds would be timed out by the browser, the
proxy and the load balancer at three different points.

Run:
    uvicorn careercompass.api.app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2
from fastapi import FastAPI, File, Form, Query, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from careercompass.api import schemas
from careercompass.api.auth import log_auth_state, service_token_middleware
from careercompass.api.errors import (
    Problem,
    problem_handler,
    unhandled_handler,
    validation_handler,
)
from careercompass.api.jobs import (
    ExtractionJob,
    ExtractionQueue,
    JobStore,
    cache_key_for,
    new_job_id,
    queue_size,
)
from careercompass.api.runtime import required_ok, runtime, warmup_enabled
from careercompass.config import EXTRACTED_DIR, SKILLS_DIR, TEMP_DIR
from careercompass.db.course_maps import CourseMapVersionConflict
from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.artifacts import cached_by_files
from careercompass.parsing.grades import grade_to_points, normalize_grade
from careercompass.parsing.transcript import (
    COURSE_CODE_RE as TRANSCRIPT_COURSE_CODE_RE,
    parse_academic_plan,
    save_extraction,
)
from careercompass.skills.extractor import extract_skills
from careercompass.skills import course_maps

logger = logging.getLogger("careercompass.api")

COURSE_LOOKUP_RE = re.compile(r"^[A-Za-z0-9._|:-]{1,266}$")
COURSE_MAP_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")

job_store = JobStore()
extraction_queue = ExtractionQueue(job_store, maxsize=queue_size())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start the worker, and warm the matcher off the critical path.

    Warm-up runs on a background thread rather than blocking start-up: a
    cold vector index build takes around 237 seconds, and an instance that
    does not accept connections for four minutes looks dead to every
    health probe pointed at it.
    """
    log_auth_state()
    from careercompass.db.connection import apply_migrations, auto_migrate_enabled

    if auto_migrate_enabled():
        # Explicit self-migration mode fails startup on a drifted/partially
        # migrated schema instead of serving broken review/storage endpoints.
        await asyncio.to_thread(apply_migrations)
    else:
        logger.info("Automatic PostgreSQL migration is disabled; schema migration skipped")
    extraction_queue.start()
    if warmup_enabled():
        runtime.warm_in_background()
    else:
        logger.info("CC_API_WARMUP=0, deferring matcher build until first use")
    try:
        yield
    finally:
        await extraction_queue.stop()


app = FastAPI(
    title="CareerCompass API",
    description=(
        "Parses course syllabi into candidate skills and resolves them onto "
        "the canonical taxonomy. See docs/SKILL_EXTRACTION_API.md."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

def _cors_origins() -> list:
    """Origins allowed to call this service from a browser.

    `["*"]` with `allow_credentials=True` is not the permissive setting it
    looks like — Starlette reflects the caller's Origin back and adds
    `Access-Control-Allow-Credentials: true`, so *any* page a developer visits
    could call this service on localhost and read the response, which includes
    parsed transcripts.

    This service is called server-to-server by the Java backend and has no
    cookies or auth headers to carry, so credentials stay off and the allowed
    origins are named. `CC_API_CORS_ORIGINS` is a comma-separated list; the
    default allows the local development front ends only.
    """
    raw = os.getenv("CC_API_CORS_ORIGINS", "").strip()
    if raw == "*":
        # Explicitly opted into, and still safe: without credentials the
        # browser will not attach cookies to the request.
        return ["*"]
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000",
            "http://localhost:8080", "http://127.0.0.1:8080"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    # Off deliberately: see _cors_origins. Turning this on requires naming
    # origins, never "*".
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Registered after CORS so it sits outside it in the stack; preflight OPTIONS is exempted
# inside the middleware itself, so the ordering costs nothing either way.
app.middleware("http")(service_token_middleware)

app.add_exception_handler(Problem, problem_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(Exception, unhandled_handler)


# ── Upload helpers ─────────────────────────────────────────────
def _max_upload_bytes() -> int:
    try:
        return max(1, int(os.getenv("CC_API_MAX_UPLOAD_MB", "20"))) * 1024 * 1024
    except ValueError:
        return 20 * 1024 * 1024


async def _read_pdf(file: UploadFile) -> bytes:
    """Read an upload into memory, refusing non-PDFs and oversized files."""
    filename = file.filename or "upload"
    if not filename.lower().endswith(".pdf"):
        raise Problem.invalid_file_type(filename)

    limit = _max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise Problem.payload_too_large(
                f"{filename!r} exceeds the {limit // (1024 * 1024)} MB upload limit."
            )
        chunks.append(chunk)

    if not total:
        raise Problem.unparseable_syllabus(f"{filename!r} is empty.")
    return b"".join(chunks)


def _user_facing(exc: Exception, temp_path: Path, filename: str) -> str:
    """A parse failure phrased in the caller's filename, not the server's.

    The parsers are handed a uuid temp path because pdfplumber needs a file, so
    their messages name it. Telling a client that
    `upload_79d937610f494082b41f30b54c6a2dee.pdf` has no text layer is both
    unhelpful and a small leak of how uploads are stored on disk.
    """
    return str(exc).replace(temp_path.name, filename)


def _parse_pdf_bytes(data: bytes, filename: str) -> dict:
    """
    Parse uploaded bytes by way of a temp file, because pdfplumber needs a path.

    Blocking: always call through asyncio.to_thread.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = TEMP_DIR / f"upload_{uuid.uuid4().hex}.pdf"
    temp_path.write_bytes(data)
    try:
        syllabus = parse_syllabus(str(temp_path))
    except ValueError as exc:
        raise Problem.unparseable_syllabus(_user_facing(exc, temp_path, filename)) from exc
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass

    # The parser records the temp filename it was handed; the caller cares
    # about the name the user uploaded.
    syllabus["source_file"] = filename
    return syllabus


@app.get("/", include_in_schema=False)
def root():
    """
    Send the bare host to the documentation.

    Without this, opening the service in a browser answers 404, which
    reads as a broken deployment rather than an API with no root resource.
    """
    return RedirectResponse(url="/docs")


# ── Health ─────────────────────────────────────────────────────
@app.get("/api/v1/health/live", tags=["health"])
def health_live():
    """Liveness: the process is up. Touches no model, index or database."""
    return {"status": "ok", "service": "CareerCompass API"}


@app.get("/api/v1/health/ready", response_model=schemas.ReadyResponse, tags=["health"])
def health_ready(response: Response):
    """
    Readiness: this instance can actually serve matches.

    Separate from liveness on purpose. A cold index build takes minutes,
    and an orchestrator that probes liveness during it restarts the
    container forever.
    """
    checks = runtime.health()
    ready = required_ok(checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Retry-After"] = "30"
    return {"ready": ready, "checks": checks}


# ── Transcript ─────────────────────────────────────────────────
def _parse_transcript_bytes(data: bytes, filename: str) -> dict:
    """Parse uploaded bytes via a temp file. Blocking; call in a thread."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = TEMP_DIR / f"transcript_{uuid.uuid4().hex}.pdf"
    temp_path.write_bytes(data)
    try:
        return parse_academic_plan(str(temp_path))
    except ValueError as exc:
        raise Problem.unparseable_transcript(_user_facing(exc, temp_path, filename)) from exc
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def _canonical_transcript_courses(raw_courses: list[dict]) -> list[dict]:
    """Project parser rows onto the typed cross-service transcript contract.

    ``all_courses`` intentionally remains untouched for legacy callers.  This
    view normalises the fields Java needs and reports only facts the parser can
    support.  In particular, no numeric confidence is manufactured: a value is
    exposed only when an upstream parser explicitly supplied one in the valid
    0..1 range.
    """
    codes = []
    for raw_course in raw_courses:
        code = str((raw_course or {}).get("course_code") or "").strip().upper()
        if code:
            codes.append(code)
    duplicate_codes = {code for code in codes if codes.count(code) > 1}

    courses = []
    for raw_course in raw_courses:
        raw_course = raw_course or {}
        course_code = str(raw_course.get("course_code") or "").strip().upper()
        course_name = str(raw_course.get("course_name") or "").strip()

        raw_grade = raw_course.get("grade")
        grade = normalize_grade(str(raw_grade)) if raw_grade is not None else None
        status_value = str(raw_course.get("status") or "").strip().lower()

        raw_warnings = raw_course.get("warnings")
        warnings = (
            [str(warning).strip() for warning in raw_warnings if str(warning).strip()]
            if isinstance(raw_warnings, list)
            else []
        )

        if not course_code:
            warnings.append("Course code is missing.")
        elif not TRANSCRIPT_COURSE_CODE_RE.fullmatch(course_code):
            warnings.append("Course code does not match the supported MEU format.")
        if course_code in duplicate_codes:
            warnings.append("Course code appears more than once in the transcript.")
        if not course_name:
            warnings.append("Course name is missing.")
        if grade is not None and grade_to_points(grade) is None:
            warnings.append("Grade is not recognized on the MEU scale.")
        if status_value == "passed" and grade is None:
            warnings.append("Passed course has no grade.")

        confidence = None
        raw_confidence = raw_course.get("confidence")
        if raw_confidence is not None:
            if (
                isinstance(raw_confidence, bool)
                or not isinstance(raw_confidence, (int, float))
                or not math.isfinite(raw_confidence)
                or not 0.0 <= raw_confidence <= 1.0
            ):
                warnings.append("Parser confidence is invalid and was omitted.")
            else:
                confidence = float(raw_confidence)

        # Keep insertion order while avoiding duplicate messages if an upstream
        # parser already supplied one of the deterministic warnings above.
        warnings = list(dict.fromkeys(warnings))
        low_confidence = raw_course.get("low_confidence") is True or bool(warnings)

        courses.append({
            "course_code": course_code,
            "course_name": course_name,
            "grade": grade,
            "confidence": confidence,
            "low_confidence": low_confidence,
            "warnings": warnings,
        })
    return courses


@app.post("/api/v1/transcripts/parse", response_model=schemas.TranscriptResponse,
          tags=["transcript"])
async def parse_transcript(
    file: UploadFile = File(..., description="MEU academic plan PDF"),
    save: bool = Form(False, description="Persist the extraction to data/extracted"),
):
    """
    Extract student information and course history from an academic plan PDF.

    Synchronous, unlike syllabus extraction: this parser is regex over
    pdfplumber text with no model in the path, so a full 74-course plan
    resolves in about a quarter of a second.

    `save` defaults to **false**. A transcript carries a student's name, id
    and complete grade history, so writing it to disk is an explicit
    request rather than a side effect of reading it.
    """
    data = await _read_pdf(file)
    filename = file.filename or "transcript.pdf"
    parsed = await asyncio.to_thread(_parse_transcript_bytes, data, filename)

    student = parsed.get("student") or {}
    if not student.get("student_id") and not parsed.get("all_courses"):
        raise Problem.unparseable_transcript(
            f"{filename!r} yielded neither a student id nor any courses; it "
            "does not look like an MEU academic plan."
        )

    saved_to = None
    if save:
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXTRACTED_DIR / f"{Path(filename).stem}.json"
        await asyncio.to_thread(save_extraction, parsed, str(output_path))
        saved_to = str(output_path)

    return {
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "source_file": filename,
        "student": student,
        "summary": parsed.get("summary") or {},
        "categories": parsed.get("categories") or [],
        "all_courses": parsed.get("all_courses") or [],
        "courses": _canonical_transcript_courses(parsed.get("all_courses") or []),
        "saved_to": saved_to,
    }


# ── Extraction ─────────────────────────────────────────────────
@app.post("/api/v1/syllabi/preview", response_model=schemas.PreviewResponse,
          tags=["extraction"])
async def preview_syllabus(
    file: UploadFile = File(..., description="Course syllabus PDF"),
    min_weight: float = Form(0.0, ge=0.0, le=1.0),
):
    """
    Parse a syllabus and return candidate terms without taxonomy matching.

    Fast (about a second) because it runs no model, and persists nothing.
    The upload screen calls this so the user can confirm the right
    document before committing ninety seconds of compute.
    """
    data = await _read_pdf(file)
    filename = file.filename or "upload.pdf"
    syllabus = await asyncio.to_thread(_parse_pdf_bytes, data, filename)
    skills = await asyncio.to_thread(extract_skills, syllabus)

    terms = [
        {
            "term": skill["term"],
            "level": skill["level"],
            "weight": skill["weight"],
            "evidence_count": skill["evidence_count"],
            "sources": skill["sources"],
        }
        for skill in skills
        if skill["weight"] >= min_weight
    ]
    return {
        "course_code": syllabus.get("course_code"),
        "course_title": syllabus.get("course_title"),
        "description": syllabus.get("description"),
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "total_terms": len(terms),
        "terms": terms,
        "warnings": syllabus.get("warnings") or [],
    }


@app.post("/api/v1/extractions", response_model=schemas.ExtractionResponse,
          status_code=status.HTTP_202_ACCEPTED, tags=["extraction"])
async def create_extraction(
    response: Response,
    file: UploadFile = File(..., description="Course syllabus PDF"),
    use_llm: bool = Form(None, description="Overrides CC_MATCH_LLM for this job"),
    force: bool = Form(False, description="Bypass the idempotency cache"),
    store: bool = Form(True, description="Also write results to PostgreSQL"),
):
    """
    Queue a full extraction: extract, match and store.

    The PDF is parsed synchronously first — it costs about a second, and
    it is the only way a malformed document can be reported as a 4xx.
    Once the job is accepted, every later failure is a job status, not an
    HTTP status.
    """
    data = await _read_pdf(file)
    filename = file.filename or "upload.pdf"
    content_sha256 = hashlib.sha256(data).hexdigest()

    # Fails with 503 while the index is still warming, before any parsing.
    runtime.require()

    cache_key = cache_key_for(content_sha256, store=store, use_llm=use_llm)
    if not force:
        cached = job_store.find_succeeded(cache_key)
        if cached is not None:
            response.status_code = status.HTTP_200_OK
            return cached.to_dict()

    syllabus = await asyncio.to_thread(_parse_pdf_bytes, data, filename)
    if not syllabus.get("course_code"):
        raise Problem.missing_course_code(filename, syllabus.get("warnings") or [])

    job = ExtractionJob(
        extraction_id=new_job_id(),
        content_sha256=content_sha256,
        cache_key=cache_key,
        filename=filename,
        syllabus=syllabus,
        use_llm=use_llm,
        store=store,
        warnings=list(syllabus.get("warnings") or []),
    )
    extraction_queue.submit(job)

    response.headers["Location"] = f"/api/v1/extractions/{job.extraction_id}"
    return job.to_dict()


@app.get("/api/v1/extractions", tags=["extraction"])
def list_extractions(limit: int = Query(20, ge=1, le=200)):
    """
    Recently tracked extraction jobs, newest first.

    Exists so a lost `extraction_id` can be recovered. The store is in
    memory, so this lists only jobs submitted since the last restart.
    """
    jobs = job_store.list(limit)
    return {
        "total": len(jobs),
        "items": [
            {
                "extraction_id": job.extraction_id,
                "status": job.status,
                "course_code": job.course_code,
                "filename": job.filename,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
            }
            for job in jobs
        ],
    }


@app.get("/api/v1/extractions/{extraction_id}", response_model=schemas.ExtractionResponse,
         tags=["extraction"])
def get_extraction(extraction_id: str):
    """Poll an extraction. Progress advances during the matching stage."""
    job = job_store.get(extraction_id)
    if job is None:
        raise Problem.extraction_not_found(extraction_id)
    return job.to_dict()


@app.delete("/api/v1/extractions/{extraction_id}", response_model=schemas.ExtractionResponse,
            tags=["extraction"])
def cancel_extraction(extraction_id: str):
    """
    Cancel a queued or running extraction.

    Partial results are discarded: a half-matched course is worse than no
    course, because nothing downstream can tell the two apart.
    """
    job = job_store.get(extraction_id)
    if job is None:
        raise Problem.extraction_not_found(extraction_id)
    if job.finished:
        raise Problem.extraction_not_cancellable(extraction_id, job.status)
    job.cancel_requested = True
    return job.to_dict()


# ── Content-manager review and publication ────────────────────
def _taxonomy_search_score(skill: dict, query: str):
    """Stable relevance ordering without invoking the semantic matcher."""
    from careercompass.skills.taxonomy import normalize

    label = normalize(skill.get("label") or "")
    aliases = [normalize(alias) for alias in skill.get("aliases") or []]
    description = normalize(skill.get("description") or "")
    if not query:
        return (0, label, skill["id"])
    if label == query:
        rank = 0
    elif label.startswith(query):
        rank = 1
    elif query in aliases:
        rank = 2
    elif query in label:
        rank = 3
    elif any(alias.startswith(query) for alias in aliases):
        rank = 4
    elif any(query in alias for alias in aliases):
        rank = 5
    elif query in description:
        rank = 6
    else:
        return None
    return (rank, label, skill["id"])


@app.get(
    "/api/v1/taxonomy/skills",
    response_model=schemas.TaxonomySkillSearchResponse,
    tags=["content-manager"],
)
def search_taxonomy_skills(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
):
    """Search canonical skills for the content manager's replace/add control."""
    from careercompass.skills.taxonomy import normalize

    taxonomy = runtime.require().taxonomy
    query = normalize(q)
    ranked = []
    for skill in taxonomy.skills:
        score = _taxonomy_search_score(skill, query)
        if score is not None:
            ranked.append((score, skill))
    ranked.sort(key=lambda item: item[0])

    return {
        "total": len(ranked),
        "items": [
            {
                "skill_id": skill["id"],
                "label": skill["label"],
                "skill_type": skill["skill_type"],
                "source": skill["source"],
                "description": skill.get("description") or "",
                "taxonomy_version": taxonomy.version,
            }
            for _, skill in ranked[:limit]
        ],
    }


@app.put(
    "/api/v1/course-maps/{course_map_version}",
    response_model=schemas.CourseMapPublicationResponse,
    tags=["content-manager"],
)
async def publish_reviewed_course_map(
    course_map_version: str,
    request: schemas.CourseMapPublicationRequest,
    response: Response,
):
    """Publish one complete, canonical, accepted-only course map.

    Versions are immutable idempotency keys.  The same version and canonical
    payload can be retried safely; reusing it for changed content is a 409.
    """
    if not COURSE_MAP_VERSION_RE.fullmatch(course_map_version):
        raise Problem.invalid_course_map(
            "course_map_version must be 1-120 characters and contain only "
            "letters, digits, '.', '_', ':' or '-'."
        )

    taxonomy = runtime.require().taxonomy
    if request.taxonomy_version != taxonomy.version:
        raise Problem.taxonomy_version_conflict(
            request.taxonomy_version, taxonomy.version
        )

    unknown = sorted(
        skill.skill_id
        for skill in request.skills
        if taxonomy.index.get(skill.skill_id) is None
    )
    if unknown:
        raise Problem.invalid_course_map(
            "Every approved skill must use a current canonical ID; unknown: "
            + ", ".join(unknown)
        )

    try:
        document = course_maps.build_course_map_document(
            course_map_version=course_map_version,
            institution_code=request.institution_code,
            catalog_version=request.catalog_version,
            course_code=request.course_code,
            source_outcome_id=request.source_outcome_id,
            taxonomy_version=request.taxonomy_version,
            approved_skills=[skill.model_dump() for skill in request.skills],
            taxonomy=taxonomy,
        )
        published = await asyncio.to_thread(
            course_maps.publish_course_map, document, SKILLS_DIR
        )
    except CourseMapVersionConflict as exc:
        raise Problem.course_map_version_conflict(course_map_version) from exc
    except psycopg2.Error as exc:
        logger.warning("Course-map publication database write failed: %s", exc)
        raise Problem.database_unavailable(
            "Publication metadata could not be stored. No course map was exposed."
        ) from exc
    except ValueError as exc:
        raise Problem.invalid_course_map(str(exc)) from exc

    record = published.record
    response.status_code = status.HTTP_200_OK
    return {
        "course_map_version": course_map_version,
        "course_key": published.qualified_course_key,
        "course_code": request.course_code,
        "taxonomy_version": request.taxonomy_version,
        "total_skills": len(request.skills),
        "content_sha256": published.payload_sha256,
        "published_at": record.published_at,
        "idempotent": record.idempotent,
    }


# ── Results ────────────────────────────────────────────────────
def _read_course(course_code: str) -> dict:
    import json

    if not COURSE_LOOKUP_RE.fullmatch(course_code):
        raise Problem.course_not_found(course_code)

    candidates = []
    if SKILLS_DIR.exists():
        for path in sorted(SKILLS_DIR.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                logger.warning("Skipping unreadable skills file: %s", path)
                continue
            qualified_key = document.get("qualified_course_key")
            codes = document.get("course_codes") or [document.get("course_code")]
            if course_code == qualified_key or course_code in codes:
                candidates.append(document)

    if not candidates:
        raise Problem.course_not_found(course_code)
    if len(candidates) > 1:
        raise Problem.course_code_ambiguous(
            course_code,
            [
                document.get("qualified_course_key")
                or document.get("course_code")
                or course_code
                for document in candidates
            ],
        )
    return candidates[0]


def _current_match_summary(document: dict) -> dict:
    """Recount a document after human-review overlays have changed its rows."""
    summary = dict(document.get("match_summary") or {})
    by_status = {}
    by_method = {}
    skills = document.get("skills") or []
    for skill in skills:
        match = skill.get("match") or {}
        review_status = match.get("review_status", "no_match")
        method = match.get("match_method") or "none"
        by_status[review_status] = by_status.get(review_status, 0) + 1
        by_method[method] = by_method.get(method, 0) + 1
    summary.update({"total": len(skills), "by_status": by_status, "by_method": by_method})
    return summary


@app.get("/api/v1/courses", response_model=schemas.CourseListResponse, tags=["results"])
def list_courses():
    """Every course that has been extracted, with its counts by review status."""
    import json

    courses = []
    # The same file list the skill vector joins against, so this endpoint and the vector can
    # never disagree about which courses exist.
    for path in _course_skill_paths():
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Skipping unreadable skills file: %s", path)
            continue
        document_skills = document.get("skills") or []
        runtime.overlay_reviewed_matches(document_skills)
        courses.append({
            "course_code": document.get("course_code") or Path(path).stem,
            "total_skills": document.get("total_skills", 0),
            "taxonomy_version": document.get("taxonomy_version"),
            # The file's own flag, not an inference from where it sits, so a synthetic course
            # stays labelled even if the corpus is later moved.
            "synthetic": bool(document.get("mock")),
            "by_status": _current_match_summary(document)["by_status"],
        })
    return {"total": len(courses), "courses": courses}


@app.get("/api/v1/courses/{course_code}/skills", tags=["results"])
def get_course_skills_endpoint(
    course_code: str,
    status_filter: str = Query("accepted", alias="status",
                               pattern="^(accepted|needs_review|no_match|all)$"),
    min_weight: float = Query(0.0, ge=0.0, le=1.0),
    include: str = Query("", description="Comma-separated: evidence, candidates"),
):
    """
    A course's matched skills — the endpoint the Skill Vector builder consumes.

    Defaults to accepted matches only, because that is the only status
    downstream scoring should ever see: a needs_review row still carries
    the skill_id the matcher proposed, so an unfiltered join would treat
    an unconfirmed guess as fact.

    The audit fields (evidence, candidates) are large and omitted unless
    asked for by name.
    """
    document = _read_course(course_code)
    runtime.overlay_reviewed_matches(document.get("skills") or [])
    wanted = {part.strip() for part in include.split(",") if part.strip()}

    skills = []
    for skill in document.get("skills", []):
        review_status = (skill.get("match") or {}).get("review_status", "no_match")
        if status_filter != "all" and review_status != status_filter:
            continue
        if skill.get("weight", 0.0) < min_weight:
            continue

        trimmed = dict(skill)
        if "evidence" not in wanted:
            trimmed.pop("evidence", None)
        match = dict(trimmed.get("match") or {})
        if match and "candidates" not in wanted:
            match.pop("candidates", None)
        if match:
            trimmed["match"] = match
        skills.append(trimmed)

    return {
        "course_code": document.get("course_code", course_code),
        "taxonomy_version": document.get("taxonomy_version"),
        "match_summary": _current_match_summary(document),
        "total_skills": len(skills),
        "skills": skills,
    }


# ── Skill vector and gap ───────────────────────────────────────
def _taxonomy_skill(skill_id: str) -> dict:
    """One taxonomy entry, for callers that need a label and description.

    Served from the matcher's already-loaded taxonomy. This was a line-by-line
    scan of taxonomy.jsonl on every quiz request, re-reading 903 records the
    process was already holding in memory. The file is still the fallback for
    the window before warm-up finishes.
    """
    import json

    from careercompass.config import TAXONOMY_PATH

    taxonomy = runtime.taxonomy_if_ready()
    if taxonomy is not None:
        record = taxonomy.index.get(skill_id)
        if record is not None:
            return record
        raise Problem.skill_not_found(skill_id)

    if Path(TAXONOMY_PATH).exists():
        with Path(TAXONOMY_PATH).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("id") == skill_id:
                    return record
    raise Problem.skill_not_found(skill_id)



@cached_by_files(lambda paths, taxonomy_version=None, review_revision=0: paths)
def _load_course_skills(paths: tuple, taxonomy_version=None, review_revision=0) -> dict:
    """Parse the course → skill map, cached on the fingerprint of every file.

    Keyed on `taxonomy_version` as well, because `load_course_skills` resolves
    retired canonical ids through the alias index as it loads: a taxonomy
    rebuild changes the result without touching any of these files.
    """
    from careercompass.skills.vector import load_course_skills

    mapping = load_course_skills(paths, taxonomy=runtime.taxonomy_if_ready())
    seen = set()
    for skills in mapping.values():
        # Plan-edition aliases point several course codes at the same list.
        # Apply once so the count/logging remains meaningful.
        if id(skills) in seen:
            continue
        seen.add(id(skills))
        runtime.overlay_reviewed_matches(skills)
    return mapping


def _course_skill_map() -> dict:
    if not SKILLS_DIR.exists():
        return {}
        
    paths = list(SKILLS_DIR.glob("*.json"))
    if os.getenv("CC_INCLUDE_MOCK_COURSES") == "1":
        from careercompass.config import DATA_DIR
        mock_dir = DATA_DIR / "mock" / "skills"
        if mock_dir.exists():
            paths.extend(mock_dir.glob("*.json"))
            
    taxonomy = runtime.taxonomy_if_ready()
    return _load_course_skills(
        tuple(sorted(paths)),
        taxonomy_version=getattr(taxonomy, "version", None),
        review_revision=runtime.review_revision,
    )


def _course_skill_paths() -> tuple:
    """Every course→skill file to load, real ones first.

    Order matters on a code collision: a real extracted syllabus must win over a synthetic one,
    because `load_course_skills` keeps the last write for a code and the real document is the
    one the university actually issued. There are no collisions today; this keeps that safe if a
    real syllabus is later extracted for a course the mock corpus already covers.
    """
    from careercompass.config import INCLUDE_MOCK_COURSES, MOCK_SKILLS_DIR

    paths = sorted(SKILLS_DIR.glob("*.json")) if SKILLS_DIR.exists() else []
    if INCLUDE_MOCK_COURSES and Path(MOCK_SKILLS_DIR).exists():
        real_codes = {path.stem for path in paths}
        paths += [path for path in sorted(Path(MOCK_SKILLS_DIR).glob("*.json"))
                  if path.stem not in real_codes]
    return tuple(paths)


@cached_by_files(lambda paths: paths)
def _read_synthetic_codes(paths: tuple) -> frozenset:
    """Every course code the synthetic corpus answers to, aliases included.

    Aliases matter because plan editions renumber — a transcript quotes whichever code its own
    plan uses, and the vector joins on any of them. Counting only the filename would under-report
    how much of a student's profile is synthetic, which is the one direction this number must
    not be wrong in.
    """
    codes = set()
    for path in paths:
        try:
            record = json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("course_code"):
            codes.add(record["course_code"])
        codes.update(record.get("course_codes") or [])
    return frozenset(codes)


def _synthetic_codes() -> frozenset:
    """The synthetic course codes currently loaded; empty when the corpus is off."""
    from careercompass.config import INCLUDE_MOCK_COURSES, MOCK_SKILLS_DIR

    if not INCLUDE_MOCK_COURSES or not Path(MOCK_SKILLS_DIR).exists():
        return frozenset()
    return _read_synthetic_codes(tuple(sorted(Path(MOCK_SKILLS_DIR).glob("*.json"))))


def _requirements(career_path: str) -> list:
    """One career path's requirements, with skill_type filled from the taxonomy."""
    from careercompass.config import TAXONOMY_PATH
    from careercompass.skills.gap import attach_skill_types, load_requirements
    from careercompass.skills.ontology import ONTOLOGY_PATH

    if not Path(ONTOLOGY_PATH).exists():
        raise Problem.career_path_not_found(career_path)

    rows = load_requirements(ONTOLOGY_PATH, career_path)
    if not rows:
        known = {r.get("career_path") for r in load_requirements(ONTOLOGY_PATH)}
        raise Problem.career_path_not_found(career_path, known)

    if Path(TAXONOMY_PATH).exists():
        attach_skill_types(rows, TAXONOMY_PATH)
    return rows


def _path_summary(career_path: str = None) -> dict:
    """The ontology header entry behind a path — sample size and skill count.

    Separate from `_requirements` because the denominator lives in the file's
    header rather than on the rows, and a missing header must not fail a gap:
    the arithmetic is complete without it, only the evidence line is poorer.
    """
    from careercompass.skills.gap import load_path_summary
    from careercompass.skills.ontology import ONTOLOGY_PATH

    if not Path(ONTOLOGY_PATH).exists():
        return {}
    return load_path_summary(ONTOLOGY_PATH, career_path)


def _market_captured_at() -> str:
    """When the postings behind the ontology were collected.

    Read from the scrape report rather than hard-coded, so a re-scrape moves
    the date the dashboard shows without anybody remembering to edit it.
    Absent report, absent date — never a guess.
    """
    from careercompass.config import RAW_DATA_DIR

    report = Path(RAW_DATA_DIR) / "scrape_report.json"
    if not report.exists():
        return None
    try:
        return json.loads(report.read_text(encoding="utf-8")).get("finished_at")
    except (ValueError, OSError):
        return None


# What each skip reason means to somebody reading the error, singular and plural.
_SKIP_REASONS = {
    "not passed": ("was not passed, so it carries no credit",
                   "were not passed, so they carry no credit"),
    "no skill map": ("has no extracted syllabus yet",
                     "have no extracted syllabus yet"),
}


def _no_profile_detail(vector: dict, submitted: int) -> str:
    """Say which reason actually applied, rather than assuming one.

    The message used to read "None of the submitted courses have an extracted
    skill map" whatever happened, so a course skipped for an F grade was
    reported as missing a syllabus it in fact had — 84 skills of it. The reason
    is already computed per course; it was being thrown away.
    """
    counts = {}
    for skipped in vector["courses_skipped"]:
        reason = skipped.get("reason") or "were skipped"
        counts[reason] = counts.get(reason, 0) + 1

    noun = "course" if submitted == 1 else "courses"
    if not counts:
        return f"None of the {submitted} submitted {noun} produced any skills."

    parts = []
    for reason, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        phrasing = _SKIP_REASONS.get(reason)
        if phrasing is None:
            parts.append(f"{count} {reason}")
        else:
            parts.append(f"{count} {phrasing[0] if count == 1 else phrasing[1]}")
    return (f"No skills could be derived: of {submitted} submitted {noun}, "
            + ", and ".join(parts) + ". See courses_skipped for the detail.")


def _with_coverage(payload: dict, vector: dict) -> dict:
    """Carry M2's coverage caveat onto whatever M3 or M4 built from it.

    The vector reports `courses_counted` and `courses_skipped`; the gap built
    from the very same call reported neither, and the gap is the one a student
    is shown. On the reference transcript that meant serving
    "Python: no evidence, top priority" while silently dropping 30 of the
    student's 74 courses for having no syllabus extracted yet.

    "You have not studied this" and "we could not see your courses" are
    different sentences and the caller cannot tell them apart without these.
    """
    payload["courses_counted"] = vector.get("courses_counted", 0)
    payload["courses_skipped"] = vector.get("courses_skipped", [])
    # How many of *this student's counted courses* rest on a synthetic syllabus — not how many
    # synthetic courses exist. The corpus size is the same 96 for everybody and says nothing
    # about the profile on screen; what a reader needs to know is how much of their own result
    # is built on invented coursework. Zero unless the demo corpus is enabled.
    payload["synthetic_counted"] = vector.get("synthetic_counted", 0)
    return payload


def _build_vector(request) -> dict:
    from careercompass.skills.taxonomy import TAXONOMY_VERSION
    from careercompass.skills.vector import apply_quiz_results, build_skill_vector

    course_skills = _course_skill_map()
    if not course_skills:
        raise Problem.no_skill_profile(
            "No courses have been extracted, so a transcript has nothing to join to.")

    vector = build_skill_vector(
        [course.model_dump() for course in request.courses],
        course_skills,
        taxonomy_version=TAXONOMY_VERSION,
        include_unpassed=request.include_unpassed,
        synthetic_codes=_synthetic_codes(),
    )
    if request.quiz_scores:
        # An unknown id would otherwise be injected into the vector with the
        # raw id as its label, where it joins to no requirement and silently
        # inflates total_skills. A typo should be a 404, not a phantom skill.
        taxonomy = runtime.taxonomy_if_ready()
        if taxonomy is not None:
            for skill_id in request.quiz_scores:
                if taxonomy.index.get(skill_id) is None:
                    raise Problem.skill_not_found(skill_id)
        apply_quiz_results(vector, request.quiz_scores)

    if not vector["skills"]:
        raise Problem.no_skill_profile(_no_profile_detail(vector, len(request.courses)),
                                       courses_skipped=vector["courses_skipped"])
    return vector


# ── Career-path requirements ───────────────────────────────────
#
# The ontology on its own, with no student in it. Every other endpoint in this
# section needs a transcript first, which left a caller with nothing to show
# somebody who has not uploaded one — and "what does this career actually ask
# for" is answerable without knowing anything about them.
#
# The path name is a query parameter rather than a path segment because two of
# the nine names contain a slash ("UI/UX Design"). Encoding that into a path
# segment works in theory and is rejected or silently normalised by enough
# proxies in practice that it is not worth the bug.
@app.get("/api/v1/career-paths", response_model=schemas.CareerPathListResponse,
         tags=["skill-gap"])
def list_career_paths():
    """Every career path the ontology covers, and how much evidence is behind it."""
    summary = _path_summary()
    if not summary:
        raise Problem.career_path_not_found("(none)")

    return schemas.CareerPathListResponse(
        total=len(summary),
        derived_from="job_postings",
        captured_at=_market_captured_at(),
        career_paths=[
            schemas.CareerPathSummary(
                career_path=name,
                sample_size=entry.get("sample_size") or 0,
                total_skills=entry.get("skills") or 0,
            )
            for name, entry in sorted(summary.items())
        ],
    )


@app.get("/api/v1/career-paths/skills",
         response_model=schemas.CareerPathSkillsResponse, tags=["skill-gap"])
def career_path_skills(
    career_path: str = Query(min_length=1, max_length=120),
    band: str = Query(None, pattern="^(critical|important|useful)$"),
    include_soft: bool = Query(True),
):
    """
    What one career path demands, ranked by how much of the market asks for it.

    Bands come from `gap.demand_band`, the same function the gap analysis uses,
    so a skill cannot read `critical` here and `important` there.
    """
    from careercompass.skills.gap import BANDS, SOFT_TYPE, demand_band
    from careercompass.skills.taxonomy import TAXONOMY_VERSION

    rows = _requirements(career_path)

    skills = []
    band_totals = {name: 0 for name in BANDS}
    for row in rows:
        if not include_soft and row.get("skill_type") == SOFT_TYPE:
            continue
        row_band = demand_band(row.get("coverage"))
        # Counted before the band filter, so the totals still describe the
        # whole path when the caller is looking at one band of it.
        band_totals[row_band] += 1
        if band and row_band != band:
            continue
        skills.append(schemas.CareerPathSkill(
            skill_id=row["skill_id"],
            label=row.get("skill_label") or row["skill_id"],
            skill_type=row.get("skill_type"),
            posting_count=row.get("posting_count"),
            coverage=float(row.get("coverage") or 0.0),
            demand_band=row_band,
            required_level=row.get("required_level"),
            required_score=row.get("required_score"),
            sample_terms=sorted(row.get("terms") or [])[:5],
        ))

    # Most-demanded first: this list is read top-down as an order to learn in.
    skills.sort(key=lambda s: (-s.coverage, s.label))

    return schemas.CareerPathSkillsResponse(
        career_path=career_path,
        sample_size=_path_summary(career_path).get("sample_size"),
        derived_from="job_postings",
        captured_at=_market_captured_at(),
        taxonomy_version=TAXONOMY_VERSION,
        total=len(skills),
        band_totals=band_totals,
        skills=skills,
    )


@app.post("/api/v1/skill-vector", response_model=schemas.SkillVectorResponse,
          tags=["skill-gap"])
def build_vector(request: schemas.SkillVectorRequest):
    """
    The Student Skill Vector (M2) — what a transcript implies the student knows.

    Stateless by design: this service holds no users, so the caller sends the
    confirmed transcript rows and gets the vector back. Identity and storage
    belong to the platform service.

    Deterministic arithmetic, no model involved. The same transcript and the
    same course → skill map always produce the same numbers.
    """
    return _build_vector(request)


@app.post("/api/v1/skill-gap", response_model=schemas.SkillGapResponse,
          tags=["skill-gap"])
def build_gap(request: schemas.SkillGapRequest):
    """
    The Skill Gap (M3) — the vector subtracted from a career path's requirements.

    `career_path` is the path **name**, never a numeric id, so neither service
    owns the other's identifiers.

    Every number here is computed arithmetically. `narrative` is the single
    generated field, it is off by default because it costs an LLM call, and it
    explains numbers that are already final — it can never change one. If the
    model is unavailable the gap is returned complete with `narrative` null,
    rather than failing.
    """
    from careercompass.skills.gap import build_skill_gap, write_narrative

    vector = _build_vector(request)
    gap = build_skill_gap(
        vector,
        _requirements(request.career_path),
        career_path=request.career_path,
        include_soft=request.include_soft,
        sample_size=_path_summary(request.career_path).get("sample_size"),
    )
    gap["captured_at"] = _market_captured_at()
    if request.narrative:
        write_narrative(gap)
    return _with_coverage(gap, vector)


# ── Course recommendations ─────────────────────────────────────
@app.post("/api/v1/recommendations", response_model=schemas.RecommendationResponse,
          tags=["recommendations"])
def recommend(request: schemas.RecommendationRequest):
    """
    Courses that close the gaps in a skill profile (M4).

    Items are **retrieved from the catalog and re-ranked, never generated**, so
    the service cannot invent a course that does not exist and every item
    carries a real URL. That is why M4 waited for real catalog data rather than
    being filled with synthetic rows: a wrong skill match is invisible, but a
    dead course link is something the student clicks.

    Ranking combines what closing the gap is worth — `priority` already weights
    the shortfall by market demand — with how well the course fits: a student
    who has never touched a skill is sent the introduction, not the masterclass,
    and a course that only mentions a skill in passing ranks far below one that
    names it in its title.

    `explanation` is written from the student's own gap, never from the course
    description. The platforms' catalog text is not licensed for republication,
    and the gap makes for better advice anyway.

    An empty catalog answers 503 rather than an empty list: no recommendations
    because nothing has been ingested is a different thing from no
    recommendations because the student has no gaps.
    """
    from careercompass.skills.course_index import load_index
    from careercompass.skills.gap import build_skill_gap
    from careercompass.skills.recommend import recommend_courses

    index = load_index()
    if not index:
        raise Problem.catalog_unavailable(
            "No course catalog has been built. Run: "
            "python -m careercompass.cli.build_course_catalog --platform coursera")

    vector = _build_vector(request)
    gap = build_skill_gap(
        vector,
        _requirements(request.career_path),
        career_path=request.career_path,
        include_soft=request.include_soft,
    )
    return _with_coverage(
        recommend_courses(
            gap, index,
            limit=request.limit,
            platform=request.platform,
            skill_id=request.skill_id,
            language=request.language,
            per_skill=request.per_skill,
            include_soft=request.include_soft,
        ),
        vector,
    )


# ── Quizzes ────────────────────────────────────────────────────
@app.post("/api/v1/quizzes", response_model=schemas.QuizResponse,
          status_code=status.HTTP_201_CREATED, tags=["quiz"])
def create_quiz(request: schemas.QuizRequest):
    """
    Generate a multiple-choice quiz for one skill (M5).

    Returns the questions **and** the answer key. The calling service stores
    both, shows the student only the questions, and grades the submission
    itself — grading is arithmetic and needs no model. It then feeds the score
    back through `POST /api/v1/skill-vector` as `quiz_scores`, which already
    replaces the grade-inferred proficiency.

    Holding the key here would give this service user-scoped state it has none
    of anywhere else. `API_DESIGN.md`'s concern is the key reaching the
    browser; a server-to-server response does not.

    Unlike the skill-gap narrative, an unavailable model is fatal: there is no
    partial quiz worth returning, so this answers 503 rather than an empty one.
    """
    from careercompass.skills.llm import LLMDecider
    from careercompass.skills.quiz import generate_quiz

    skill = _taxonomy_skill(request.skill_id)

    decider = LLMDecider()
    if not decider.available:
        raise Problem.llm_unavailable(
            getattr(decider, "reason_unavailable", "the configured model is not reachable"))

    try:
        return generate_quiz(
            skill,
            request.question_count,
            decider=decider,
            verify=request.verify,
        )
    except RuntimeError as exc:
        # Every candidate question failed validation. That is a model-quality
        # problem, not a bad request, so it reads as a dependency failure.
        raise Problem.llm_unavailable(str(exc)) from exc


# ── Mentor matching ────────────────────────────────────────────
@app.post("/api/v1/mentor-matches", response_model=schemas.MentorMatchResponse,
          tags=["matching"])
def match_mentors(request: schemas.MentorMatchRequest):
    """
    Rank supplied mentors against one student's skill gap (M6).

    Mentors are ranked against what the student is **missing**, not what they already know:
    a mentor matched to a strength is the one who can teach them least. Weighting is by
    `priority`, so a mentor who covers a small shortfall the market asks for constantly
    outranks one who covers a large shortfall almost nobody hires for.

    The caller supplies the mentors — already filtered for status and authorisation — and no
    id can come back that did not go in. This service stores no mentor records.

    Read `signal` on every item before displaying it. `stated` means the mentor's own
    expertise resolved onto the taxonomy. `inferred` means only a study field was available
    and a career path stood in for it; that must not be shown to a student as though the
    mentor had claimed the skill. Deterministic throughout — no model is involved, and the
    same request always produces the same ranking.
    """
    from careercompass.skills.gap import build_skill_gap
    from careercompass.skills.mentor_matching import build_mentor_matches

    vector = _build_vector(request)
    gap = build_skill_gap(
        vector,
        _requirements(request.career_path),
        career_path=request.career_path,
        include_soft=request.include_soft,
    )

    # Only pay for the matcher when a mentor actually stated expertise. Building it cold
    # costs minutes, and a request where every mentor falls back to their study field would
    # otherwise be billed for an index it never consults.
    needs_matcher = any(mentor.expertise_terms for mentor in request.mentors)
    matcher = runtime.matcher_for(False) if needs_matcher else None

    return build_mentor_matches(
        gap,
        [mentor.model_dump() for mentor in request.mentors],
        matcher=matcher,
        limit=request.limit,
    )


# ── Ad-hoc matching ────────────────────────────────────────────
@app.post("/api/v1/skills/match", response_model=schemas.MatchResponse, tags=["matching"])
async def match_terms(request: schemas.MatchRequest):
    """
    Match up to 25 free-text terms with no PDF involved.

    The cap is hard rather than advisory: Ollama serialises inference, so
    an unbounded batch here is an accidental denial of service against the
    one worker every extraction also depends on.
    """
    if len(request.terms) > schemas.MAX_MATCH_TERMS:
        raise Problem.payload_too_large(
            f"{len(request.terms)} terms requested; this endpoint accepts at "
            f"most {schemas.MAX_MATCH_TERMS}. Submit a syllabus through "
            "/api/v1/extractions for bulk work."
        )

    matcher = runtime.matcher_for(request.use_llm)

    def _match_all():
        return [matcher.match(item.term, item.evidence) for item in request.terms]

    matches = await asyncio.to_thread(_match_all)
    decider = matcher.decider
    return {
        "total": len(matches),
        # Same rule as the job worker: degraded means the LLM was wanted
        # and unreachable, not that it is switched off by configuration.
        "degraded": decider.enabled and not decider.available,
        "matches": matches,
    }


# ── Human review ───────────────────────────────────────────────
@app.get("/api/v1/review-queue", response_model=schemas.ReviewQueueResponse,
         tags=["review"])
async def review_queue(
    limit: int = Query(100, ge=1, le=500),
    course_code: str = Query("", description="Optional course filter"),
):
    """
    Terms the matcher would not decide, worst score first.

    Not a peripheral endpoint: on the benchmark run 50 of 93 ambiguous
    terms landed here, which makes review throughput the real bottleneck
    of the whole subsystem.
    """
    from careercompass.db.skills import get_review_queue

    try:
        items = await asyncio.to_thread(get_review_queue, limit)
    except Exception as exc:  # noqa: BLE001
        raise Problem.database_unavailable(str(exc).strip().splitlines()[0][:200]) from exc

    if course_code:
        items = [item for item in items if item["course_code"] == course_code]
    return {"total": len(items), "items": items}


@app.post("/api/v1/review-queue/decisions", response_model=schemas.ReviewDecisionsResponse,
          tags=["review"])
async def record_decisions(request: schemas.ReviewDecisionsRequest):
    """
    Record reviewer decisions in a batch, because reviewing happens in sittings.

    Decisions are stored against the normalised term rather than the
    course, so one correction applies everywhere the term appears and
    survives the next matcher run.
    """
    import psycopg2

    from careercompass.db.skills import record_review

    def _record_all():
        recorded = 0
        errors = []
        for decision in request.decisions:
            try:
                record_review(
                    decision.term, decision.skill_id, decision.decision,
                    reviewer=request.reviewer, note=decision.note,
                )
                runtime.set_reviewed_decision(
                    decision.term, decision.skill_id, decision.decision,
                )
                recorded += 1
            except ValueError as exc:
                errors.append({"term": decision.term, "error": str(exc)})
            except psycopg2.errors.ForeignKeyViolation:
                # A skill_id that is not in the taxonomy is the reviewer's
                # mistake, not a database outage. Reporting it as 503 told the
                # caller to retry something that can never succeed, and leaked
                # the constraint name while doing it.
                errors.append({
                    "term": decision.term,
                    "error": f"{decision.skill_id!r} is not in the taxonomy",
                })
        return recorded, errors

    try:
        recorded, errors = await asyncio.to_thread(_record_all)
    except Exception as exc:  # noqa: BLE001
        raise Problem.database_unavailable(str(exc).strip().splitlines()[0][:200]) from exc

    return {"recorded": recorded, "errors": errors}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("careercompass.api.app:app", host="0.0.0.0", port=8000, reload=True)
