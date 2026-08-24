"""
CareerCompass API — Error contract

Every failure the pipeline can raise maps to one `Problem`, serialised as
RFC 9457 `application/problem+json`. The alternative the service started
with was a blanket 500 wrapper around the whole handler, which told a
client nothing it could act on: a scanned PDF, an unreachable database
and a genuine bug all looked identical from outside.

Usage:
    raise Problem.unparseable_syllabus("no text layer in scan.pdf")
"""

from fastapi import Request
from fastapi.responses import JSONResponse

CONTENT_TYPE = "application/problem+json"


class Problem(Exception):
    """An API failure with a machine-readable type and an HTTP status."""

    def __init__(self, status: int, type_: str, title: str, detail: str = "",
                 headers: dict = None, **extra):
        super().__init__(detail or title)
        self.status = status
        self.type = type_
        self.title = title
        self.detail = detail
        self.headers = headers or {}
        self.extra = extra

    def to_dict(self) -> dict:
        payload = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            payload["detail"] = self.detail
        payload.update(self.extra)
        return payload

    # ── Upload and parsing ─────────────────────────────────────
    @classmethod
    def invalid_file_type(cls, filename: str):
        return cls(
            400, "invalid-file-type", "Only PDF uploads are supported",
            f"{filename!r} is not a .pdf file.",
        )

    @classmethod
    def payload_too_large(cls, detail: str):
        return cls(413, "payload-too-large", "Request payload too large", detail)

    @classmethod
    def unparseable_syllabus(cls, detail: str, warnings: list = None):
        return cls(
            422, "unparseable-syllabus", "Syllabus could not be parsed", detail,
            warnings=warnings or [],
        )

    @classmethod
    def unparseable_transcript(cls, detail: str):
        return cls(
            422, "unparseable-transcript", "Transcript could not be parsed", detail,
        )

    @classmethod
    def missing_course_code(cls, filename: str, warnings: list = None):
        return cls(
            422, "missing-course-code", "No course code found in the syllabus",
            f"{filename!r} parsed, but no course code was found, so the result "
            "has no stable key to store under.",
            warnings=warnings or [],
        )

    # ── Jobs ───────────────────────────────────────────────────
    @classmethod
    def extraction_not_found(cls, extraction_id: str):
        """
        A 404 that says what a valid id looks like.

        Users reach for the course code or the output path here, because
        those are the identifiers they already have. Saying only "not
        found" leaves them guessing, so the detail names the right format
        and the endpoint they probably wanted instead.
        """
        looks_like_course_code = extraction_id.isdigit()
        detail = (
            f"No extraction with id {extraction_id!r}. Extraction ids come from "
            "the 202 response of POST /api/v1/extractions and look like "
            "'ext_d37e7f4edc45'. Job history is held in memory and is lost on "
            "restart; GET /api/v1/extractions lists what is still tracked."
        )
        if looks_like_course_code:
            detail += (
                f" To read stored results for course {extraction_id}, use "
                f"GET /api/v1/courses/{extraction_id}/skills instead."
            )
        return cls(404, "extraction-not-found", "Unknown extraction", detail)

    @classmethod
    def extraction_not_cancellable(cls, extraction_id: str, status: str):
        return cls(
            409, "extraction-not-cancellable", "Extraction already finished",
            f"Extraction {extraction_id!r} is {status} and cannot be cancelled.",
        )

    @classmethod
    def queue_full(cls, size: int):
        return cls(
            507, "queue-full", "Extraction queue is full",
            f"All {size} queue slots are occupied. Retry once a running "
            "extraction finishes.",
            headers={"Retry-After": "60"},
        )

    # ── Results ────────────────────────────────────────────────
    @classmethod
    def course_not_found(cls, course_code: str):
        return cls(
            404, "course-not-found", "No skills stored for this course",
            f"Course {course_code!r} has not been extracted yet.",
        )

    @classmethod
    def career_path_not_found(cls, career_path: str, known: list = None):
        known = ", ".join(sorted(known or []))
        return cls(
            404, "career-path-not-found", "Unknown career path",
            f"No requirements are derived for {career_path!r}."
            + (f" Known paths: {known}." if known else ""),
        )

    @classmethod
    def no_skill_profile(cls, detail: str, courses_skipped: list = None):
        """
        Why no profile could be built, per course.

        `courses_skipped` is carried because the reason differs per course and
        the caller cannot guess it: a course skipped for an F grade and one
        skipped for having no extracted syllabus are the same 422 otherwise,
        and the fix is different in each case.
        """
        return cls(
            422, "no-skill-profile", "No skill profile could be built", detail,
            courses_skipped=courses_skipped or [],
        )

    @classmethod
    def skill_not_found(cls, skill_id: str):
        return cls(
            404, "skill-not-found", "Unknown skill", 
            f"{skill_id!r} is not in the taxonomy.",
        )

    # ── Dependencies ───────────────────────────────────────────
    @classmethod
    def matcher_unavailable(cls, detail: str):
        return cls(
            503, "matcher-unavailable", "Skill matcher is not ready", detail,
            headers={"Retry-After": "30"},
        )

    @classmethod
    def llm_unavailable(cls, detail: str):
        return cls(
            503, "llm-unavailable", "No language model is available", detail,
            headers={"Retry-After": "30"},
        )

    @classmethod
    def catalog_unavailable(cls, detail: str):
        return cls(
            503, "catalog-unavailable", "No course catalog is available", detail,
            headers={"Retry-After": "300"},
        )

    @classmethod
    def database_unavailable(cls, detail: str):
        return cls(
            503, "database-unavailable", "Database is unreachable", detail,
            headers={"Retry-After": "30"},
        )

    # ── Service authentication ─────────────────────────────────
    @classmethod
    def not_authenticated(cls, detail: str):
        """
        The caller did not present a valid service token.

        This authenticates the *calling service*, not a student — no end-user identity
        crosses this boundary. `WWW-Authenticate` is required on a 401 by RFC 9110 and tells
        the caller which scheme to retry with.
        """
        return cls(
            401, "not-authenticated", "Service authentication required", detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def validation_handler(request: Request, exc) -> JSONResponse:
    """
    Render FastAPI's request-validation failures in the same shape as everything else.

    Without this the API speaks two error dialects: problem+json for
    pipeline failures and FastAPI's `{"detail": [...]}` for schema
    failures, so a client needs two parsers for one service.
    """
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        status_code=422,
        content={
            "type": "invalid-request",
            "title": "Request validation failed",
            "status": 422,
            "errors": jsonable_encoder(exc.errors()),
        },
        media_type=CONTENT_TYPE,
    )


async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
    """Render a Problem as application/problem+json."""
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict(),
        headers=exc.headers,
        media_type=CONTENT_TYPE,
    )


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Last resort for genuine bugs.

    Deliberately opaque: an unexpected exception's message can carry file
    paths and connection strings, so the detail stays in the server log
    and the client gets the status only.
    """
    return JSONResponse(
        status_code=500,
        content={
            "type": "internal-error",
            "title": "Unexpected server error",
            "status": 500,
        },
        media_type=CONTENT_TYPE,
    )
