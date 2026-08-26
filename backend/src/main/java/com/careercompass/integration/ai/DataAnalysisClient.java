package com.careercompass.integration.ai;

import com.careercompass.integration.dto.*;

/**
 * The Integration Layer's contract with Mohammed's Python/FastAPI Data Analyses service
 * (Section 5.1, Container-level architecture — the "AI agent" box, talked to over REST rather
 * than in-process, per the design decisions we worked through together).
 *
 * Two implementations exist:
 *   - {@link MockDataAnalysisClient} — returns realistic fake data; active by default
 *     (`careercompass.ai-service.use-mock=true`), lets the whole Java backend be built and
 *     tested end-to-end without the Python service existing yet.
 *   - {@link HttpDataAnalysisClient} — real HTTP calls via WebClient; active once
 *     `careercompass.ai-service.use-mock=false` and Mohammed's service is reachable.
 *
 * Callers (services) depend ONLY on this interface, never on which implementation is active —
 * this is what makes swapping mock for real a one-line config change rather than a code
 * change (NFR-MNT-01/02).
 *
 * Method signatures describe WHAT is needed, not HOW the Python service is internally shaped —
 * see our earlier discussion on containing the blast radius of any future contract mismatch to
 * just the HttpDataAnalysisClient implementation and these DTOs, never the callers.
 */
public interface DataAnalysisClient {

    /** Module 1 — Transcript Analysis: PDF parsing + LLM structuring (Section 5.3.3). */
    TranscriptExtractionResponse extractTranscript(TranscriptExtractionRequest request);

    /** Module 2 — deterministic Skill Vector construction (Section 5.3.3). */
    SkillVectorResponse buildSkillVector(BuildSkillVectorRequest request);

    /** Module 3 — Skill-Gap Analysis and Dashboard (Section 5.3.3). */
    SkillGapAnalysisResponse analyzeSkillGap(SkillGapAnalysisRequest request);

    /** Module 4 — Course Recommendation (Section 5.3.3). */
    java.util.List<RecommendedCourseDto> recommendCourses(CourseRecommendationRequest request);

    /** Module 5 — Quiz generation (Section 5.3.3). */
    QuizGenerationResponse generateQuiz(QuizGenerationRequest request);

    /** Module 6 — Job Matching, scored against a single job (Section 5.3.3). */
    JobMatchResponse scoreJobMatch(JobMatchRequest request);

    /** M6 — Mentor Matching against student gaps. */
    MentorMatchResponse matchMentors(MentorMatchRequest request);

    /** M8 — queue a syllabus extraction proposal. This must not publish a course map. */
    SyllabusExtractionResponse submitSyllabusExtraction(SyllabusExtractionRequest request);

    /** M8 — read current progress or the completed extraction proposal. */
    SyllabusExtractionResponse getSyllabusExtraction(String extractionId);

    /** M8 — cancel an extraction which has not reached a terminal state. */
    SyllabusExtractionResponse cancelSyllabusExtraction(String extractionId);

    /** Search the AI-owned canonical taxonomy for manual additions and replacements. */
    java.util.List<TaxonomySkillSuggestion> searchTaxonomySkills(String query, int limit);

    /** Publish one complete, content-manager-approved course map idempotently. */
    PublishCourseMapResponse publishCourseMap(PublishCourseMapRequest request);

    /**
     * Fast read-only scan of a syllabus PDF (no matching, no persistence) used to
     * pre-fill the upload form's course identity fields.
     */
    SyllabusPreviewResponse previewSyllabusPdf(String filename, String contentType, byte[] content);
}
