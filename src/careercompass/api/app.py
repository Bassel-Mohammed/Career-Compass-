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
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from careercompass.api import schemas
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
from careercompass.parsing.syllabus import parse_syllabus
from careercompass.parsing.transcript import parse_academic_plan, save_extraction
from careercompass.skills.extractor import extract_skills

logger = logging.getLogger("careercompass.api")

COURSE_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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

    cache_key = cache_key_for(content_sha256)
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


# ── Results ────────────────────────────────────────────────────
def _course_path(course_code: str) -> Path:
    if not COURSE_CODE_RE.match(course_code):
        raise Problem.course_not_found(course_code)
    return SKILLS_DIR / f"{course_code}.json"


def _read_course(course_code: str) -> dict:
    import json

    path = _course_path(course_code)
    if not path.exists():
        raise Problem.course_not_found(course_code)
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/v1/courses", response_model=schemas.CourseListResponse, tags=["results"])
def list_courses():
    """Every course that has been extracted, with its counts by review status."""
    import json

    courses = []
    if SKILLS_DIR.exists():
        for path in sorted(SKILLS_DIR.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                logger.warning("Skipping unreadable skills file: %s", path)
                continue
            courses.append({
                "course_code": document.get("course_code") or path.stem,
                "total_skills": document.get("total_skills", 0),
                "taxonomy_version": document.get("taxonomy_version"),
                "by_status": (document.get("match_summary") or {}).get("by_status", {}),
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
        "match_summary": document.get("match_summary", {}),
        "total_skills": len(skills),
        "skills": skills,
    }


# ── Skill vector and gap ───────────────────────────────────────
def _taxonomy_skill(skill_id: str) -> dict:
    """One taxonomy entry, for callers that need a label and description."""
    import json

    from careercompass.config import TAXONOMY_PATH

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



def _course_skill_map() -> dict:
    """The course → skill map, keyed by every code each course is known by.

    The loaded taxonomy is passed in so canonical ids retired by a merge are
    repointed at load time rather than silently failing to join against the
    career-path ontology. The matcher already holds it, so this costs no I/O.
    """
    from careercompass.skills.vector import load_course_skills

    if not SKILLS_DIR.exists():
        return {}
    taxonomy = runtime.taxonomy_if_ready()
    return load_course_skills(SKILLS_DIR.glob("*.json"), taxonomy=taxonomy)


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
    )
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
