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


# ── Skill vector and gap ───────────────────────────────────────
class TranscriptCourse(BaseModel):
    """One row of a confirmed transcript.

    ``course_codes`` carries every code the course is known by. Plan editions
    renumber, so a transcript quoting 0433301 must still join to a skill map
    holding A0413301 for the same course.
    """
    course_code: str = Field(min_length=1, max_length=20)
    course_codes: list[str] = Field(default_factory=list, max_length=8)
    course_name: Optional[str] = Field(None, max_length=200)
    grade: Optional[str] = Field(None, max_length=8)
    status: Optional[str] = Field(None, max_length=30)
    credit_hours: Optional[int] = Field(None, ge=0, le=20)


class SkillVectorRequest(BaseModel):
    courses: list[TranscriptCourse] = Field(min_length=1, max_length=200)
    quiz_scores: dict[str, float] = Field(default_factory=dict)
    include_unpassed: bool = False


class SkillVectorResponse(BaseModel):
    taxonomy_version: Optional[str] = None
    source: str
    total_skills: int
    courses_counted: int
    courses_skipped: list[dict[str, Any]]
    skills: list[dict[str, Any]]


class SkillGapRequest(SkillVectorRequest):
    # A career path *name*, never Java's numeric id: the two services agreed
    # to key on names so neither owns the other's identifiers.
    career_path: str = Field(min_length=1, max_length=120)
    include_soft: bool = True
    narrative: bool = False


class SkillGapResponse(BaseModel):
    career_path: Optional[str] = None
    taxonomy_version: Optional[str] = None
    source: Optional[str] = None
    summary: dict[str, int]
    total_requirements: int
    requirements_met: int
    skills: list[dict[str, Any]]
    narrative: Optional[str] = None


# ── Course recommendations ─────────────────────────────────────
class RecommendationRequest(SkillGapRequest):
    """A gap request plus the knobs that shape which courses come back."""
    limit: int = Field(10, ge=1, le=50)
    platform: Optional[str] = Field(None, pattern="^(coursera|ocw|youtube)$")
    skill_id: Optional[str] = Field(None, max_length=120)
    language: Optional[str] = Field("en", max_length=10)
    per_skill: int = Field(3, ge=1, le=10)
    include_soft: bool = False


class RecommendedCourse(BaseModel):
    course_id: str
    title: str
    platform: str
    # Never empty. The design requires every item carry a real link, because
    # this is the one output a student clicks rather than reads.
    url: str
    level: Optional[str] = None
    language: Optional[str] = None
    duration_hours: Optional[float] = None
    rating: Optional[float] = None


class RecommendationItem(BaseModel):
    skill_id: str
    skill_label: Optional[str] = None
    course: RecommendedCourse
    relevance: float
    matched_in_title: bool
    explanation: str


class RecommendationResponse(BaseModel):
    career_path: Optional[str] = None
    total: int
    items: list[RecommendationItem]
    # Which gaps the catalog cannot currently serve — the honest answer to
    # "why is there nothing here for X", and the list that says what to widen.
    skills_without_courses: list[str] = Field(default_factory=list)


# ── Quizzes ────────────────────────────────────────────────────
class QuizRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
    # Capped because Ollama serialises inference: an unbounded count here is
    # an accidental denial of service against every other caller, the same
    # reason /skills/match caps its batch.
    question_count: int = Field(5, ge=1, le=10)
    verify: bool = True


class QuizQuestion(BaseModel):
    question_id: str
    question: str
    options: list[str]


class QuizResponse(BaseModel):
    skill_id: Optional[str] = None
    skill_label: Optional[str] = None
    question_count: int
    questions: list[QuizQuestion]
    # Returned to the calling service, which stores it and shows the student
    # only `questions`. Server-to-server, so the key never reaches a browser.
    answer_key: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


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
