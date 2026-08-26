"""
CareerCompass API — Request and response models

The result document is passed through as the pipeline builds it rather
than re-modelled here. That is deliberate: `save_skills` already defines
the shape written to data/extracted/skills, and duplicating it in Pydantic
would create two definitions that drift apart the first time a field is
added. The models below cover the envelopes the API itself owns.
"""

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
JobStage = Literal["queued", "parsing", "extracting", "matching", "storing", "done"]
ReviewStatus = Literal["accepted", "needs_review", "no_match"]
Decision = Literal["confirmed", "corrected", "rejected"]

MAX_MATCH_TERMS = 25

# A quiz score is a fraction of the questions answered correctly, never a
# percentage. See SkillVectorRequest.quiz_scores.
QuizScore = Annotated[float, Field(ge=0.0, le=1.0)]


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
    description: Optional[str] = None
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


class CanonicalTranscriptCourse(BaseModel):
    """Stable, review-oriented view of one parsed transcript row.

    The current deterministic parser does not calculate a probability for a
    row, so ``confidence`` is normally null.  Concrete extraction anomalies
    are carried separately in ``warnings`` and make ``low_confidence`` true;
    callers must not mistake that flag for a fabricated numeric score.
    """

    course_code: str
    course_name: str
    grade: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    low_confidence: bool = False
    warnings: list[str] = Field(default_factory=list)


class TranscriptResponse(BaseModel):
    content_sha256: str
    source_file: str
    student: StudentInfo
    summary: TranscriptSummary
    categories: list[TranscriptCategory] = []
    all_courses: list[dict[str, Any]] = []
    courses: list[CanonicalTranscriptCourse] = Field(
        default_factory=list,
        description=(
            "Canonical typed course rows for service integration. The legacy "
            "all_courses field remains available during migration."
        ),
    )
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
    # True when this course's skills come from a synthetic syllabus rather than a real extracted
    # document. Carried so no consumer has to infer it from a directory name.
    synthetic: bool = False
    by_status: dict[str, int] = {}


class CourseListResponse(BaseModel):
    total: int
    courses: list[CourseSummary]


# ── Content-manager publication ───────────────────────────────
class TaxonomySkill(BaseModel):
    skill_id: str
    label: str
    skill_type: str
    source: str
    description: str = ""
    taxonomy_version: str


class TaxonomySkillSearchResponse(BaseModel):
    total: int
    items: list[TaxonomySkill]


class ApprovedCourseSkill(BaseModel):
    """One canonical skill approved by a content manager.

    There is deliberately no review-status field here.  Presence in a
    publication request means the row is approved; allowing callers to submit
    ``needs_review`` would make it possible for a proposal to leak into student
    vectors through the publication endpoint.
    """

    skill_id: str = Field(min_length=1, max_length=120)
    skill_label: Optional[str] = Field(None, max_length=300)
    term: str = Field(min_length=1, max_length=300)
    level: Literal["beginner", "intermediate", "advanced"]
    weight: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0, le=10000)
    sources: list[str] = Field(default_factory=list, max_length=30)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=500)

    @field_validator("skill_id", "term")
    @classmethod
    def _strip_required_skill_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("skill_label")
    @classmethod
    def _strip_optional_skill_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("sources")
    @classmethod
    def _normalise_sources(cls, values: list[str]) -> list[str]:
        cleaned = []
        seen = set()
        for raw in values:
            value = str(raw).strip()
            if not value:
                continue
            if len(value) > 40:
                raise ValueError("source names must be at most 40 characters")
            if value not in seen:
                cleaned.append(value)
                seen.add(value)
        return cleaned


class CourseMapPublicationRequest(BaseModel):
    # The backend derives institution codes as ``uni:<id>`` (colon included), so the
    # pattern must accept it — see docs/contracts/careercompass-ai-internal-v1.yaml,
    # which deliberately declares no character restriction beyond length here.
    institution_code: str = Field(min_length=1, max_length=120,
                                  pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    catalog_version: str = Field(min_length=1, max_length=80,
                                 pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    course_code: str = Field(min_length=1, max_length=64,
                             pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    source_outcome_id: str = Field(min_length=1, max_length=120)
    taxonomy_version: str = Field(min_length=1, max_length=120)
    skills: list[ApprovedCourseSkill] = Field(min_length=1, max_length=1000)

    @field_validator("institution_code", "course_code")
    @classmethod
    def _normalise_codes(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("catalog_version", "source_outcome_id", "taxonomy_version")
    @classmethod
    def _strip_publication_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("skills")
    @classmethod
    def _reject_duplicate_skill_ids(cls, skills: list[ApprovedCourseSkill]):
        seen = set()
        duplicates = set()
        for skill in skills:
            if skill.skill_id in seen:
                duplicates.add(skill.skill_id)
            seen.add(skill.skill_id)
        if duplicates:
            raise ValueError(
                "skill_id must be unique; repeated: " + ", ".join(sorted(duplicates))
            )
        return skills


class CourseMapPublicationResponse(BaseModel):
    course_map_version: str
    course_key: str
    course_code: str
    taxonomy_version: str
    total_skills: int
    content_sha256: str
    published_at: str
    idempotent: bool


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
    # Bounded, because the clamp downstream is silent. A caller sending a
    # percentage (85) rather than a fraction (0.85) would otherwise be clamped
    # to 1.0 and get HTTP 200 — turning a D-minus student into a perfect one
    # with no signal that anything was wrong. Out of range is a 422.
    quiz_scores: dict[str, QuizScore] = Field(default_factory=dict)
    include_unpassed: bool = False


class SkillVectorResponse(BaseModel):
    taxonomy_version: Optional[str] = None
    source: str
    total_skills: int
    courses_counted: int
    # Of `courses_counted`, how many rest on a synthetic syllabus rather than a real extracted
    # one. Zero unless the demo corpus is enabled. Reported so the caller can label it: a
    # profile built on invented coursework must not be presented as one built on real records.
    synthetic_counted: int = 0
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
    # The same counts split by how much of the market asks for each
    # requirement, so a dashboard can say "you meet 4 of the 11 things this
    # career insists on" instead of "4 of 129 requirements", which is true
    # and useless. Keyed critical / important / useful.
    band_summary: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Postings behind this path's requirements — the denominator under every
    # `importance`. Null when the ontology header is missing; the arithmetic
    # is unaffected, only the evidence line is poorer.
    sample_size: Optional[int] = None
    # When those postings were collected, so a consumer can date its own claim rather than
    # hard-coding one that goes stale on the next scrape.
    captured_at: Optional[str] = None
    total_requirements: int
    requirements_met: int
    skills: list[dict[str, Any]]
    narrative: Optional[str] = None
    # How much of the transcript this gap could actually see. A requirement can
    # read "no evidence" because the student never studied it, or because the
    # course that teaches it has no syllabus extracted yet, and those are very
    # different things to show someone. Mirrors SkillVectorResponse.
    courses_counted: int = 0
    synthetic_counted: int = 0
    courses_skipped: list[dict[str, Any]] = Field(default_factory=list)


# ── Career-path requirements ───────────────────────────────────
class CareerPathSkill(BaseModel):
    """One thing a career path asks for, and the evidence that it does.

    This is the ontology row as the outside world sees it. It carries both the
    fraction and the count it came from: a dashboard that shows only "39%" is
    asking to be trusted, and one that shows "72 of 184 postings" is showing
    its working.
    """
    skill_id: str
    label: str
    skill_type: Optional[str] = None
    posting_count: Optional[int] = None
    coverage: float
    demand_band: Literal["critical", "important", "useful"]
    required_level: Optional[str] = None
    required_score: Optional[float] = None
    # A few of the phrases employers actually wrote that resolved to this
    # skill. Capped, because the full list runs to dozens on common skills and
    # nobody reads the twentieth way of writing "Python".
    sample_terms: list[str] = Field(default_factory=list)


class CareerPathSummary(BaseModel):
    career_path: str
    sample_size: int
    total_skills: int


class CareerPathListResponse(BaseModel):
    total: int
    derived_from: Optional[str] = None
    captured_at: Optional[str] = None
    career_paths: list[CareerPathSummary]


class CareerPathSkillsResponse(BaseModel):
    """What one career path demands, independent of any student.

    Exists so the market can be shown before a transcript is uploaded. Every
    other skill endpoint needs a student's courses first, which left the
    dashboard with nothing to say to somebody who has not uploaded one yet.
    """
    career_path: str
    sample_size: Optional[int] = None
    derived_from: Optional[str] = None
    # When the postings were collected, so the page can date its own claim.
    captured_at: Optional[str] = None
    taxonomy_version: Optional[str] = None
    total: int
    band_totals: dict[str, int] = Field(default_factory=dict)
    skills: list[CareerPathSkill]


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


class UnservedSkill(BaseModel):
    """A gap the catalog cannot currently serve.

    Carries the label as well as the id: the caller has no taxonomy to resolve
    `esco:1d86f05e-…` against, and this list exists to be read.
    """
    skill_id: str
    skill_label: Optional[str] = None


class RecommendationResponse(BaseModel):
    career_path: Optional[str] = None
    total: int
    items: list[RecommendationItem]
    # Which gaps the catalog cannot currently serve — the honest answer to
    # "why is there nothing here for X", and the list that says what to widen.
    skills_without_courses: list[UnservedSkill] = Field(default_factory=list)
    # Same caveat as SkillGapResponse: a recommendation list is only as complete
    # as the transcript the gap behind it could read.
    courses_counted: int = 0
    courses_skipped: list[dict[str, Any]] = Field(default_factory=list)


# ── Mentor matching ────────────────────────────────────────────
class Mentor(BaseModel):
    """
    One mentor the caller wants ranked.

    The caller owns mentor records; this service holds none. It supplies only the mentors a
    given student is allowed to see — already filtered for status and authorisation — and
    every id in the response will have come from this list.

    ``expertise_terms`` is optional but is the only strong signal. Without it the ranking
    falls back to what a study field implies, which is broad and is reported as such in the
    response's ``signal`` field.
    """
    mentor_id: str = Field(min_length=1, max_length=120)
    study_field: Optional[str] = Field(None, max_length=120)
    field_starting_year: Optional[int] = Field(None, ge=1950, le=2100)
    expertise_terms: list[str] = Field(default_factory=list, max_length=20)


class MentorMatchRequest(SkillGapRequest):
    """A gap request plus the mentors to rank against it."""
    mentors: list[Mentor] = Field(min_length=1, max_length=200)
    limit: int = Field(10, ge=1, le=50)

    @field_validator("mentors")
    @classmethod
    def _reject_duplicate_ids(cls, mentors: list) -> list:
        seen = set()
        duplicates = set()
        for mentor in mentors:
            if mentor.mentor_id in seen:
                duplicates.add(mentor.mentor_id)
            seen.add(mentor.mentor_id)
        if duplicates:
            # Ranking the same mentor twice would put them in the list twice, which reads as
            # a bug in the caller's list rather than an answer.
            raise ValueError(
                "mentor_id must be unique; repeated: " + ", ".join(sorted(duplicates))
            )
        return mentors


class AlignedSkill(BaseModel):
    """A gap of the student's that this mentor could help close."""
    skill_id: str
    skill_label: Optional[str] = None


class MentorMatchItem(BaseModel):
    mentor_id: str
    score: float = Field(ge=0.0, le=1.0)
    signal: Literal["stated", "inferred", "none"] = Field(
        description=(
            "What the ranking was built from. 'stated' means the mentor's own expertise "
            "terms resolved to canonical skills. 'inferred' means only their study field was "
            "available and a career path stood in for it — do not present that to a student "
            "as though the mentor claimed the skill. 'none' means neither was usable."
        )
    )
    aligned_skills: list[AlignedSkill]
    gaps_addressed: int
    years_experience: int
    explanation: str


class MentorMatchResponse(BaseModel):
    career_path: Optional[str] = None
    taxonomy_version: Optional[str] = None
    total: int
    gaps_considered: int = Field(
        description="How many open gaps the ranking had to work with. Zero means the student "
                    "has no weak or moderate skills, so every mentor scores on seniority only."
    )
    items: list[MentorMatchItem]


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
