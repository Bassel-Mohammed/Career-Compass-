/**
 * Mirrors the Java DTOs in `backend/src/main/java/com/careercompass/dto/`.
 * If one of those changes, this file changes with it.
 */

/** The `role` string AuthResponse comes back with. */
export type Role =
  | 'JOB_SEEKER'
  | 'EMPLOYER'
  | 'EXPERT'
  | 'CONTENT_MANAGER'
  | 'ADMIN';

/**
 * The two roles that can create their own account. The other three are created
 * by an administrator and can only sign in — see AuthController, which has no
 * /register route for them.
 */
export type SelfRegisterRole = Extract<Role, 'JOB_SEEKER' | 'EMPLOYER'>;

/** AuthResponse — returned by every login and register endpoint. */
export interface AuthResponse {
  token: string;
  tokenType: string;
  role: Role;
  userId: number;
  email: string;
  expiresInSeconds: number;
}

/** LoginRequest — shared by all five actors; the endpoint carries the role. */
export interface LoginRequest {
  email: string;
  password: string;
}

/** RegisterJobSeekerRequest */
export interface RegisterJobSeekerRequest {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
}

/** RegisterEmployerRequest — industry and companyDescription are optional. */
export interface RegisterEmployerRequest {
  companyName: string;
  industry?: string;
  email: string;
  password: string;
  companyDescription?: string;
}

/** One entry of ApiErrorResponse.fieldErrors, from a @Valid failure. */
export interface FieldError {
  field: string;
  message: string;
}

/** ApiErrorResponse — the single error shape the whole API uses. */
export interface ApiErrorResponse {
  timestamp?: string;
  status: number;
  error: string;
  message: string;
  path?: string;
  fieldErrors?: FieldError[];
}

/** The session we keep in the browser. */
export interface Session {
  token: string;
  role: Role;
  userId: number;
  email: string;
  /** Epoch milliseconds, derived from expiresInSeconds at the moment of login. */
  expiresAt: number;
}

/* ===========================================================================
   Reference data — GET /api/reference/*
   Readable by any signed-in actor. Feeds every study-field, career-path and
   university selector in the app.
   =========================================================================== */

export interface StudyFieldResponse {
  studyFieldId: number;
  fieldName: string;
}

export interface UniversityResponse {
  universityId: number;
  universityName: string;
}

export interface CareerPathResponse {
  careerPathId: number;
  title: string;
  description?: string;
  /** Expanded objects, not ids — so "paths for my field" filters client-side. */
  studyFields: StudyFieldResponse[];
  createdAt: string;
}

/* ===========================================================================
   Job seeker profile — /api/job-seekers/me
   =========================================================================== */

export interface JobSeekerProfileResponse {
  jobseekerId: number;
  firstName: string;
  lastName: string;
  email: string;
  universityId?: number;
  universityName?: string;
  studyFieldId?: number;
  studyFieldName?: string;
  careerPathId?: number;
  careerPathTitle?: string;
  createdAt: string;
  lastLoginAt?: string;
}

/**
 * Partial update: only non-null fields are applied. Omitting a field leaves it
 * unchanged — there is no way to clear one back to null through this endpoint.
 */
export interface UpdateJobSeekerProfileRequest {
  firstName?: string;
  lastName?: string;
  universityId?: number;
  studyFieldId?: number;
  careerPathId?: number;
}

/* ===========================================================================
   Transcript — upload, review, confirm
   =========================================================================== */

export interface ExtractedCourseItem {
  courseCode?: string;
  courseName?: string;
  grade?: string;
  /**
   * ⚠️ The one score in this API on a 0.0..1.0 scale. Every other score is
   * already 0..100 — the backend converts them in `HttpDataAnalysisClient.toPercent`,
   * and this field is the single one that bypasses it. Multiply by 100 to display.
   * Usually absent: the AI returns a per-row probability only sometimes, and a
   * missing value must NOT be read as zero confidence.
   */
  confidence?: number;
  /** Flag the row for review. Not a numeric score — never compare it to a threshold. */
  lowConfidence: boolean;
  warnings: string[];
}

export interface TranscriptReviewResponse {
  courses: ExtractedCourseItem[];
  lowConfidenceCount: number;
}

/** What the student confirms after correcting the extraction. Nothing is persisted until this. */
export interface ConfirmTranscriptRequest {
  courses: {
    courseCode?: string;
    courseName: string;
    grade: string;
  }[];
}

/* ===========================================================================
   Skill dashboard
   =========================================================================== */

/**
 * How much of the job market asks for a skill, in three bands.
 *
 * Derived by the AI service from the share of a career path's scraped job postings that named
 * the skill: `critical` at or above 25%, `important` from 10%, `useful` below. Never recomputed
 * on this side — the thresholds live beside the posting data that justifies them.
 */
export type DemandBand = 'critical' | 'important' | 'useful';

/**
 * A transcript course that could not contribute to the dashboard.
 *
 * `reason` is `'no skill map'` — no syllabus extracted for it yet — or `'not passed'`. The first
 * is the system's gap, not the student's, and the page has to say which it was.
 */
export interface SkippedCourseResponse {
  courseCode?: string;
  reason?: string;
  status?: string;
}

/** Classification counts within one band. Keys are lower-case, unlike `classification`. */
export interface BandCounts {
  strong: number;
  moderate: number;
  weak: number;
  total: number;
}

export interface SkillLevelResponse {
  /**
   * ⚠️ Always absent — the service never sets it. Present only to mirror the Java
   * DTO. Use `canonicalSkillId` for anything that identifies a skill.
   */
  skillId?: number;
  /** The AI service's id. This is what a quiz request must carry. */
  canonicalSkillId?: string;
  skillName?: string;
  /** 0..100, already a percentage. Do not multiply. */
  score: number;
  /** Compare case-insensitively. */
  classification?: 'Strong' | 'Moderate' | 'Weak';
  /** Null against the real AI service — per-skill prose is not in the v1 contract. */
  explanation?: string;
  /** 0..100 target for this career path, from `requiredLevel`. Already a percentage. */
  targetScore?: number;
  /** How deeply the market wants it, not how well the student does it. */
  requiredLevel?: 'beginner' | 'intermediate' | 'advanced';
  /**
   * 0..100 — the share of this career path's job postings that asked for the skill.
   *
   * Not comparable to `score`. This says how much the skill matters; `score` says how good the
   * student is at it. Rendering them on one axis would be meaningless.
   */
  importancePercent?: number;
  demandBand?: DemandBand;
  /**
   * Postings that named this skill. Shown with `SkillDashboardResponse.sampleSize` as
   * "asked for in 72 of 184 postings" — the evidence behind the percentage.
   */
  postingCount?: number;
  /** Taxonomy type. `soft` skills top every path and are reported apart from the rest. */
  skillType?: 'knowledge' | 'skill' | 'tool' | 'soft';
  /** Shortfall weighted by demand. The order the list arrives in. */
  priority?: number;
  /** How the current score was measured. */
  evidenceSource?: 'grades' | 'grades+quizzes' | 'quizzes' | 'transfer';
  /** Confirmed transcript courses whose syllabi support this skill. */
  sourceCourses?: SkillCourseEvidenceResponse[];
}

export interface SkillCourseEvidenceResponse {
  courseCode?: string;
  courseName?: string;
  grade?: string;
  level?: 'beginner' | 'intermediate' | 'advanced';
}

export interface SkillDashboardResponse {
  jobseekerId: number;
  careerPathTitle: string;
  /** 0..100 integer. */
  overallReadinessPercent: number;
  /**
   * Pre-sorted by `priority` — shortfall weighted by market demand — so the list reads as an
   * order to work through. Do not re-sort by score: that puts every unstudied skill at the top
   * in arbitrary order, which is a list of everything not done rather than what to do next.
   */
  skills: SkillLevelResponse[];
  /** false = derived from grades alone (FR-JS-22), not from quiz evidence. */
  basedOnQuizResults: boolean;
  /** Java-issued id of this projection refresh. */
  vectorVersion?: string;
  taxonomyVersion?: string;
  /** Job postings behind this path — the denominator under every `importancePercent`. */
  sampleSize?: number;
  /** ISO-8601 — when those postings were collected. */
  marketCapturedAt?: string;
  /** Transcript courses that actually fed this dashboard. */
  coursesCounted?: number;
  /** Courses that could not be used, with the reason. Empty when everything was readable. */
  coursesSkipped?: SkippedCourseResponse[];
  /**
   * Of `coursesCounted`, how many rest on a synthetic demo syllabus rather than a real one.
   * Non-zero only when the demo corpus is enabled — and when it is, the page must say so.
   */
  syntheticCounted?: number;
  /** Classification counts per band, keyed `critical` / `important` / `useful`. */
  bandSummary?: Partial<Record<DemandBand, BandCounts>>;
  /** Plain-language summary from the AI service. Null when unavailable. */
  narrative?: string;
}

/* ===========================================================================
   Career-path market requirements

   What a career asks for, with no student in it. The one thing the dashboard can show
   truthfully before a transcript has been uploaded.
   =========================================================================== */

export interface CareerPathSkill {
  skillId: string;
  label: string;
  skillType?: 'knowledge' | 'skill' | 'tool' | 'soft';
  /** Postings that named this skill. */
  postingCount?: number;
  /** 0..100 share of the path's postings. Already a percentage. */
  coveragePercent: number;
  demandBand: DemandBand;
  requiredLevel?: 'beginner' | 'intermediate' | 'advanced';
  /** A few phrases employers actually wrote that resolved to this skill. */
  sampleTerms?: string[];
}

export interface CareerPathSkillsResponse {
  careerPath: string;
  /** Postings behind this path. */
  sampleSize?: number;
  derivedFrom?: string;
  /** ISO-8601 — when the postings were collected. */
  capturedAt?: string;
  taxonomyVersion?: string;
  total: number;
  /** Rows per band across the whole path. */
  bandTotals?: Partial<Record<DemandBand, number>>;
  skills: CareerPathSkill[];
}

/* ===========================================================================
   Course recommendations
   =========================================================================== */

export interface CourseRecommendationItem {
  recommendationId: number;
  courseName: string;
  sourceLink: string;
  /** Only returned by POST /generate — absent when read back via GET. */
  targetedSkillName?: string;
  /** Same: only on /generate. */
  explanation?: string;
  recommendedAt: string;
}

/* ===========================================================================
   Quizzes
   =========================================================================== */

export interface GenerateQuizRequest {
  /** `SkillLevelResponse.canonicalSkillId` — a string, not the numeric skillId. */
  skillId: string;
  /** 1..10, defaults to 5 server-side. Omit rather than sending null. */
  questionCount?: number;
}

/** Options are four discrete fields, not an array. The answer key is never included. */
export interface QuizQuestionView {
  questionId: number;
  questionText: string;
  optionA: string;
  optionB: string;
  optionC: string;
  optionD: string;
}

export type QuizOption = 'A' | 'B' | 'C' | 'D';

export interface QuizView {
  quizId: number;
  /** Misleadingly named in the Java DTO: this is the skill label, not a course. */
  courseName: string;
  generatedAt: string;
  /** 0..100. Absent until the quiz has been submitted. */
  score?: number;
  /** Absent until submitted — use as the "already attempted" flag. */
  takenAt?: string;
  /** May be shorter than the requested count: malformed questions are dropped server-side. */
  questions: QuizQuestionView[];
}

export interface SubmitQuizRequest {
  answers: {
    questionId: number;
    /** ⚠️ A letter, never an index. Sending 0 or "0" is a 400. */
    selectedOption: QuizOption;
  }[];
}

export interface QuizQuestionResult {
  questionId: number;
  selectedOption: QuizOption;
  correctOption: QuizOption;
  /** JSON key is `correct`, not `isCorrect`. */
  correct: boolean;
}

export interface QuizResultResponse {
  quizId: number;
  /** 0..100, already multiplied. 4 of 5 arrives as 80.00. */
  score: number;
  correctCount: number;
  /** Questions in the quiz, not answers submitted — skipped ones still count against you. */
  totalQuestions: number;
  /** One entry per submitted answer, in submission order. */
  questionResults: QuizQuestionResult[];
  /** Re-render the dashboard from this rather than refetching. */
  updatedDashboard: SkillDashboardResponse;
}

/* ===========================================================================
   Job matches — descoped, see api/jobMatches.ts
   =========================================================================== */

export interface JobMatchResult {
  jobId: number;
  jobTitle: string;
  companyName: string;
  /** 0..100. From the mock this can carry many decimal places — round for display. */
  matchScore: number;
  explanation?: string;
  matchedAt: string;
}

/* ===========================================================================
   Mentors and consultations
   =========================================================================== */

export interface MentorSummaryResponse {
  expertId: number;
  firstName: string;
  lastName: string;
  studyFieldName: string | null;
  /** A calendar year (e.g. 2015), not a duration. */
  fieldStartingYear: number;
  matchScore?: number;
  gapsAddressed?: number;
  matchReason?: string;
  /**
   * The mentor's published weekly slots. Booking outside them is rejected, and an empty
   * list means this mentor has not published a schedule and cannot be booked yet.
   */
  availability?: AvailabilitySlotResponse[];
}

export interface BookAppointmentRequest {
  expertId: number;
  /**
   * ⚠️ ISO local date-time with NO zone or offset: "2026-09-01T14:30:00".
   * `Date.toISOString()` appends a Z and fails to bind. Use `toLocalDateTime()`.
   * Must be in the future per the SERVER's clock.
   */
  appointmentDate: string;
}

export type AppointmentStatus = 'Requested' | 'Accepted' | 'Rejected' | 'Completed';

export interface AppointmentResponse {
  appointmentId: number;
  expertId: number;
  expertName: string;
  jobseekerId: number;
  jobseekerName: string;
  appointmentDate: string;
  statusName: AppointmentStatus;
  /** Expert-written. Absent on the booking response. */
  sessionNotes?: string;
  /** Carries both the feedback and the readiness evaluation — one column serves both. */
  feedback?: string;
  createdAt: string;
}

/* ===========================================================================
   Employer
   =========================================================================== */

export interface EmployerProfileResponse {
  employerId: number;
  companyName: string;
  industry?: string;
  email: string;
  companyDescription?: string;
  createdAt: string;
}

export interface UpdateEmployerProfileRequest {
  companyName?: string;
  industry?: string;
  companyDescription?: string;
}

/** PUT replaces the whole posting — always resubmit every field. */
export interface JobPostRequest {
  title: string;
  description: string;
  requiredSkills?: string;
  studyFieldId?: number;
}

export interface JobResponse {
  jobId: number;
  employerId: number;
  companyName: string;
  title: string;
  description?: string;
  requiredSkills?: string;
  studyFieldId?: number;
  studyFieldName?: string;
  skillNames: string[];
  isActive: boolean;
  postedAt: string;
}

export interface CandidateSkillInsight {
  skillName: string;
  /** 0..100. */
  score?: number;
}

export interface CandidateMatchResult {
  jobseekerId: number;
  firstName: string;
  lastName: string;
  /** Exposed deliberately: FR-EMP-13 contact happens by email, not in-app. */
  email: string;
  matchScore: number;
  explanation?: string;
  skillInsights: CandidateSkillInsight[];
  matchedAt: string;
}

/* ===========================================================================
   Expert / mentor
   =========================================================================== */

export interface ExpertResponse {
  expertId: number;
  firstName: string;
  lastName: string;
  email: string;
  studyFieldId?: number;
  studyFieldName?: string;
  fieldStartingYear: number;
  /** Only "Active" experts are visible to students browsing mentors. */
  statusName: 'Active' | 'Inactive';
}

export interface AvailabilitySlotRequest {
  /** ⚠️ 1..7 (Monday..Sunday), not 0..6. */
  dayOfWeek: number;
  /** "HH:mm:ss" */
  startTime: string;
  endTime: string;
}

export interface AvailabilitySlotResponse extends AvailabilitySlotRequest {
  availabilityId: number;
}

/** Full-week replace, never a delta — the server deletes all slots and re-inserts. */
export interface UpdateAvailabilityRequest {
  slots: AvailabilitySlotRequest[];
}

/** Both optional; a null field is left unchanged. */
export interface ConsultationOutcomeRequest {
  sessionNotes?: string;
  /** Carries the FR-EX-10 readiness evaluation too — there is no separate column. */
  feedback?: string;
}

/* ===========================================================================
   Content manager
   =========================================================================== */

export interface ContentManagerResponse {
  contentManagerId: number;
  firstName: string;
  lastName: string;
  email: string;
  universityId?: number;
  universityName?: string;
  studyFieldId?: number;
  studyFieldName?: string;
  isActive: boolean;
  createdAt: string;
}

export interface SelectStudyFieldRequest {
  studyFieldId: number;
}

export type LearningOutcomeExtractionStatus =
  | 'UPLOADED'
  | 'QUEUED'
  | 'EXTRACTING'
  | 'READY_FOR_REVIEW'
  | 'PUBLISHING'
  | 'PUBLISHED'
  | 'FAILED'
  | 'CANCELLED';

export interface LearningOutcomeResponse {
  outcomeId: number;
  /** Stable course identity. Course codes are only unique inside this scope. */
  institutionCode: string;
  catalogVersion: string;
  courseCode: string;
  courseName: string;
  description?: string;
  originalFilename?: string;
  universityName?: string;
  studyFieldName?: string;
  /** The raw PDF was removed from disk; the row and its metadata are retained. */
  deletedFromDisk: boolean;
  uploadedAt: string;
  updatedAt: string;
  extractionStatus: LearningOutcomeExtractionStatus;
  extractionError?: string;
  warnings: string[];
  taxonomyVersion?: string;
  /** Optimistic-lock token sent with every draft mutation. */
  draftRevision: number;
  courseMapVersion?: number;
  totalSkills: number;
  pendingSkills: number;
  publishedAt?: string;
}

export type DraftSkillDecision =
  | 'PENDING'
  | 'ACCEPTED'
  | 'REPLACED'
  | 'REMOVED'
  | 'ADDED';

export type SkillLevel = 'beginner' | 'intermediate' | 'advanced';

export interface DraftSkillCandidate {
  skillId: string;
  label: string;
  /** Matcher confidence, represented on the AI service's 0..1 scale. */
  score: number;
}

export interface DraftSkillResponse {
  draftSkillId: number;
  outcomeId: number;
  term: string;
  canonicalSkillId?: string;
  canonicalSkillLabel?: string;
  originalCanonicalSkillId?: string;
  originalCanonicalSkillLabel?: string;
  level: SkillLevel;
  /** Relative course contribution, on a 0..1 scale. */
  weight: number;
  evidenceCount: number;
  sources: string[];
  /** Evidence payloads vary by extractor zone; the review UI renders them defensively. */
  evidence: unknown[];
  candidates: DraftSkillCandidate[];
  matchMethod?: string;
  /** Matcher confidence, represented on the AI service's 0..1 scale. */
  matchScore?: number;
  matchReason?: string;
  aiReviewStatus?: string;
  decision: DraftSkillDecision;
  note?: string;
  /** Optimistic-lock token for this individual row. */
  rowVersion: number;
  createdAt: string;
  updatedAt: string;
}

export interface TaxonomySkillResponse {
  skillId: string;
  label: string;
  skillType?: string;
  source?: string;
  description?: string;
  taxonomyVersion?: string;
}

export interface TaxonomySkillSearchResponse {
  total: number;
  items: TaxonomySkillResponse[];
}

/** Auto-fill suggestion read back from the PDF before upload. Every field is advisory. */
export interface SyllabusPreviewResponse {
  courseCode?: string;
  courseName?: string;
  description?: string;
  contentSha256: string;
  totalTerms: number;
  warnings: string[];
}

export interface AddDraftSkillRequest {
  skillId: string;
  /** Display label from the taxonomy picker; the backend re-resolves it against the taxonomy. */
  skillLabel?: string;
  term?: string;
  level: SkillLevel;
  weight: number;
  note?: string;
  expectedDraftRevision: number;
}

export interface UpdateDraftSkillRequest {
  level?: SkillLevel;
  weight?: number;
  note?: string;
  decision?: DraftSkillDecision;
  expectedRowVersion: number;
  expectedDraftRevision: number;
}

export interface ReplaceDraftSkillRequest {
  replacementSkillId: string;
  note?: string;
  expectedRowVersion: number;
  expectedDraftRevision: number;
}

export interface DeleteDraftSkillRequest {
  expectedRowVersion: number;
  expectedDraftRevision: number;
}

export interface PublishLearningOutcomeRequest {
  expectedDraftRevision: number;
}

/* ===========================================================================
   Admin
   =========================================================================== */

export interface CreateContentManagerRequest {
  firstName: string;
  lastName: string;
  email: string;
  initialPassword: string;
  universityId: number;
  studyFieldId?: number;
}

export interface UpdateContentManagerRequest {
  firstName?: string;
  lastName?: string;
  universityId?: number;
  studyFieldId?: number;
}

export interface CreateExpertRequest {
  firstName: string;
  lastName: string;
  email: string;
  initialPassword: string;
  studyFieldId?: number;
  /** Minimum 1950. */
  fieldStartingYear: number;
}

export interface CreateStudyFieldRequest {
  fieldName: string;
}

export interface CreateUniversityRequest {
  universityName: string;
}

export interface CreateCareerPathRequest {
  title: string;
  description?: string;
  /** At least one. */
  studyFieldIds: number[];
}

/** If `studyFieldIds` is given it REPLACES the whole set — send the complete list. */
export interface UpdateCareerPathRequest {
  title?: string;
  description?: string;
  studyFieldIds?: number[];
}

/**
 * Changing your own password. The current one is required even though the request already
 * carries a valid token — a stolen session must not be enough to take over the account.
 */
export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
}
