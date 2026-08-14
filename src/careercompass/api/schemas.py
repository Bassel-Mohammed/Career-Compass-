"""
CareerCompass API — Request and response models

The result document is passed through as the pipeline builds it rather
than re-modelled here. That is deliberate: `save_skills` already defines
the shape written to data/extracted/skills, and duplicating it in Pydantic
would create two definitions that drift apart the first time a field is
added. The models below cover the envelopes the API itself owns.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
JobStage = Literal["queued", "parsing", "extracting", "matching", "storing", "done"]
ReviewStatus = Literal["accepted", "needs_review", "no_match"]
Decision = Literal["confirmed", "corrected", "rejected"]

MAX_MATCH_TERMS = 25


# ── Preview ────────────────────────────────────────────────────
class PreviewTerm(BaseModel):
    term: str
    level: str
    weight: float
    evidence_count: int
    sources: list[str]


class PreviewResponse(BaseModel):
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    content_sha256: str
    total_terms: int
    terms: list[PreviewTerm]
    warnings: list[str] = []


# ── Transcript ─────────────────────────────────────────────────
class StudentInfo(BaseModel):
    student_name: str = ""
    student_id: str = ""
    cumulative_gpa: Optional[float] = None
    rating: str = ""
    level: str = ""
    plan_hours: int = 0
    passed_hours: int = 0
    remaining_hours: int = 0
    registered_hours: int = 0


class TranscriptSummary(BaseModel):
    total_courses: int = 0
    passed_courses: int = 0
    transferred_courses: int = 0
    exempted_courses: int = 0
    in_progress_courses: int = 0
    not_registered_courses: int = 0
    total_credit_hours: int = 0
    passed_credit_hours: int = 0
    computed_gpa: Optional[float] = None
    reported_gpa: Optional[float] = None
    grade_distribution: dict[str, int] = {}


class TranscriptCategory(BaseModel):
    category_name: str
    required_hours: int = 0
    passed_hours: int = 0
    courses: list[dict[str, Any]] = []


class TranscriptResponse(BaseModel):
    content_sha256: str
    source_file: str
    student: StudentInfo
    summary: TranscriptSummary
    categories: list[TranscriptCategory] = []
    all_courses: list[dict[str, Any]] = []
    saved_to: Optional[str] = Field(
        None,
        description="Where the extraction was written, when save=true was "
                    "requested. Null means nothing was persisted.",
    )


# ── Extraction jobs ────────────────────────────────────────────
class Progress(BaseModel):
    stage: JobStage
    terms_total: int = 0
    terms_resolved: int = 0
    elapsed_seconds: float = 0.0


class ExtractionResponse(BaseModel):
    extraction_id: str
    status: JobStatus
    course_code: Optional[str] = None
    content_sha256: str
    degraded: bool = Field(
        False,
        description="True when the LLM stage was unavailable and ambiguous "
                    "terms fell through to the review queue.",
    )
    progress: Progress
    result: Optional[dict[str, Any]] = None
    warnings: list[str] = []
    error: Optional[str] = None
    created_at: str
    finished_at: Optional[str] = None


# ── Results ────────────────────────────────────────────────────
class CourseSummary(BaseModel):
    course_code: str
    total_skills: int
    taxonomy_version: Optional[str] = None
    by_status: dict[str, int] = {}


class CourseListResponse(BaseModel):
    total: int
    courses: list[CourseSummary]


# ── Ad-hoc matching ────────────────────────────────────────────
class MatchTermRequest(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    evidence: str = Field("", max_length=2000)


class MatchRequest(BaseModel):
    # The upper bound is enforced in the route rather than here, so going
    # over it answers 413 payload-too-large as the specification states,
    # instead of a generic 422 validation error.
    terms: list[MatchTermRequest] = Field(min_length=1)
    use_llm: Optional[bool] = None


class MatchResponse(BaseModel):
    total: int
    degraded: bool = False
    matches: list[dict[str, Any]]


# ── Review queue ───────────────────────────────────────────────
class ReviewItem(BaseModel):
    course_code: str
    term: str
    review_status: str
    match_score: Optional[float] = None
    candidates: list[dict[str, Any]] = []


class ReviewQueueResponse(BaseModel):
    total: int
    items: list[ReviewItem]


class ReviewDecision(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    decision: Decision
    skill_id: Optional[str] = None
    note: str = Field("", max_length=500)


class ReviewDecisionsRequest(BaseModel):
    reviewer: str = Field("", max_length=100)
    decisions: list[ReviewDecision] = Field(min_length=1, max_length=200)


class ReviewDecisionsResponse(BaseModel):
    recorded: int
    errors: list[dict[str, str]] = []


# ── Health ─────────────────────────────────────────────────────
class ReadyResponse(BaseModel):
    ready: bool
    checks: dict[str, dict[str, Any]]
