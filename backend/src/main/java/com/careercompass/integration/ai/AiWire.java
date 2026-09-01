package com.careercompass.integration.ai;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import java.util.List;
import java.util.Map;

/**
 * The Python service's wire shapes, exactly as the generated FastAPI OpenAPI schema
 * defines them.
 *
 * <p>These types exist so that snake_case field names, {@code 0.0..1.0} scales, lower-case enums
 * and zero-based answer indices stop here. {@link HttpDataAnalysisClient} is the only class
 * allowed to see them; everything above it works in {@code com.careercompass.integration.dto}
 * terms. That boundary is the whole point of the integration layer — when the AI contract moves,
 * exactly one file changes.
 *
 * <p>Every response record ignores unknown properties on purpose. The contract is allowed to add
 * fields additively, and a new optional field must never break a running backend.
 */
final class AiWire {

    private AiWire() {
    }

    // ── Shared ────────────────────────────────────────────────────────────

    /** One confirmed transcript row sent to the AI service. */
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record TranscriptCourse(
            String courseCode,
            String courseName,
            String grade) {
    }

    /**
     * RFC 9457 problem details. The AI service returns this for every error, so decoding it is
     * what turns "something went wrong" into a message naming the career path that was not
     * found and the ones that were.
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ProblemDetails(
            String type,
            String title,
            Integer status,
            String detail,
            List<String> known) {
    }

    // ── M1 transcripts ────────────────────────────────────────────────────

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record TranscriptParseResponse(List<CanonicalCourse> courses) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record CanonicalCourse(
            String courseCode,
            String courseName,
            String grade,
            Double confidence,
            boolean lowConfidence,
            List<String> warnings) {
    }

    // ── M2 skill vector ───────────────────────────────────────────────────

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillVectorRequest(
            List<TranscriptCourse> courses,
            Map<String, Double> quizScores,
            boolean includeUnpassed) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillVectorResponse(
            String taxonomyVersion,
            String source,
            Integer totalSkills,
            Integer coursesCounted,
            List<Map<String, Object>> coursesSkipped,
            List<SkillVectorItem> skills) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillVectorItem(
            String skillId,
            String label,
            Double proficiency,
            Double coverage,
            String evidence,
            Double quizScore) {
    }

    // ── M3 skill gap ──────────────────────────────────────────────────────

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillGapRequest(
            List<TranscriptCourse> courses,
            Map<String, Double> quizScores,
            boolean includeUnpassed,
            String careerPath,
            boolean includeSoft,
            boolean narrative) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillGapResponse(
            String careerPath,
            Map<String, Integer> summary,
            Map<String, Map<String, Integer>> bandSummary,
            Integer sampleSize,
            String capturedAt,
            Integer totalRequirements,
            Integer requirementsMet,
            List<SkillGapItem> skills,
            String narrative,
            Integer coursesCounted,
            Integer syntheticCounted,
            List<SkippedCourse> coursesSkipped) {
    }

    /** A transcript row the vector could not use, and why. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkippedCourse(
            String courseCode,
            String reason,
            String status) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillGapItem(
            String skillId,
            String label,
            String skillType,
            String requiredLevel,
            Double requiredProficiency,
            Double currentLevel,
            Double gap,
            String classification,
            Double importance,
            String demandBand,
            Integer postingCount,
            Double priority,
            String evidence,
            Integer courseCount,
            List<VectorCourseEvidence> courses) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record VectorCourseEvidence(
            String courseCode,
            String courseName,
            String grade,
            Double weight,
            String level) {
    }

    // ── Career-path requirements ──────────────────────────────────────────

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record CareerPathSkillsResponse(
            String careerPath,
            Integer sampleSize,
            String derivedFrom,
            String capturedAt,
            String taxonomyVersion,
            Integer total,
            Map<String, Integer> bandTotals,
            List<CareerPathSkill> skills) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record CareerPathSkill(
            String skillId,
            String label,
            String skillType,
            Integer postingCount,
            Double coverage,
            String demandBand,
            String requiredLevel,
            Double requiredScore,
            List<String> sampleTerms) {
    }

    // ── M4 recommendations ────────────────────────────────────────────────

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record RecommendationRequest(
            List<TranscriptCourse> courses,
            Map<String, Double> quizScores,
            boolean includeUnpassed,
            String careerPath,
            boolean includeSoft,
            Integer limit,
            String skillId,
            String language) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record RecommendationResponse(
            String careerPath,
            Integer total,
            List<RecommendationItem> items,
            List<UnservedSkill> skillsWithoutCourses) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record RecommendationItem(
            String skillId,
            String skillLabel,
            RecommendedCourse course,
            Double relevance,
            boolean matchedInTitle,
            String explanation) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record RecommendedCourse(
            String courseId,
            String title,
            String platform,
            String url,
            String level,
            String language) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record UnservedSkill(String skillId, String skillLabel) {
    }

    // ── M5 quizzes ────────────────────────────────────────────────────────

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record QuizRequest(String skillId, int questionCount, boolean verify) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record QuizResponse(
            String skillId,
            String skillLabel,
            Integer questionCount,
            List<QuizQuestion> questions,
            Map<String, QuizAnswer> answerKey,
            List<String> warnings) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record QuizQuestion(String questionId, String question, List<String> options) {
    }

    /** {@code correctIndex} is ZERO-BASED into the question's options. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record QuizAnswer(Integer correctIndex, String correctAnswer, String explanation) {
    }

    // ── M8 syllabus proposals and approved course maps ──────────────────

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SyllabusExtractionResponse(
            String extractionId,
            String status,
            String courseCode,
            String contentSha256,
            boolean degraded,
            ExtractionProgress progress,
            ExtractionResult result,
            List<String> warnings,
            String error,
            String createdAt,
            String finishedAt) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record ExtractionProgress(
            String stage,
            Integer termsTotal,
            Integer termsResolved,
            Double elapsedSeconds) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record ExtractionResult(
            String courseCode,
            Integer totalSkills,
            String taxonomyVersion,
            List<ExtractedSkill> skills) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record ExtractedSkill(
            String term,
            CanonicalSkill canonical,
            String level,
            Double weight,
            Integer evidenceCount,
            List<String> sources,
            List<Map<String, Object>> evidence,
            SkillMatch match) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record CanonicalSkill(String id, String label, String taxonomy) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillMatch(
            String originalTerm,
            String canonicalId,
            String canonicalLabel,
            String taxonomy,
            String taxonomyVersion,
            String matchMethod,
            Double matchScore,
            String reviewStatus,
            String reason,
            List<SkillCandidate> candidates) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record SkillCandidate(String id, String label, Double score) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    record TaxonomySearchResponse(Integer total, List<TaxonomySkill> items) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record PreviewTerm(
            String term,
            String level,
            Double weight,
            Integer evidenceCount,
            List<String> sources) {
    }

    /** Read-only syllabus scan behind the upload form's auto-fill. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record PreviewResponse(
            String courseCode,
            String courseTitle,
            String description,
            String contentSha256,
            Integer totalTerms,
            List<PreviewTerm> terms,
            List<String> warnings) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record TaxonomySkill(
            String skillId,
            String label,
            String skillType,
            String source,
            String description,
            String taxonomyVersion) {
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record PublishCourseMapRequest(
            String institutionCode,
            String catalogVersion,
            String courseCode,
            String sourceOutcomeId,
            String taxonomyVersion,
            List<ApprovedCourseSkill> skills) {
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record ApprovedCourseSkill(
            String skillId,
            String skillLabel,
            String term,
            String level,
            Double weight,
            Integer evidenceCount,
            List<String> sources,
            List<Map<String, Object>> evidence) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record PublishCourseMapResponse(
            String courseMapVersion,
            String courseKey,
            String courseCode,
            String taxonomyVersion,
            Integer totalSkills,
            String contentSha256,
            String publishedAt,
            boolean idempotent) {
    }

    // ── M6 mentor matching ──────────────────────────────────────────────────

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record MentorMatchRequest(
            String careerPath,
            List<TranscriptCourse> courses,
            Map<String, Double> quizScores,
            boolean includeSoft,
            boolean narrative,
            List<MentorDto> mentors,
            int limit) {
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record MentorDto(
            String mentorId,
            String studyField,
            Integer fieldStartingYear,
            List<String> expertiseTerms) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record MentorMatchResponse(
            String careerPath,
            String taxonomyVersion,
            Integer total,
            Integer gapsConsidered,
            List<MentorMatchItem> items) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record MentorMatchItem(
            String mentorId,
            Double score,
            String signal,
            List<AlignedSkill> alignedSkills,
            Integer gapsAddressed,
            Integer yearsExperience,
            String explanation) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record AlignedSkill(String skillId, String skillLabel) {
    }
}
