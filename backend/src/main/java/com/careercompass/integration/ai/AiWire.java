package com.careercompass.integration.ai;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import java.util.List;
import java.util.Map;

/**
 * The Python service's wire shapes, exactly as `docs/contracts/careercompass-ai-internal-v1.yaml`
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
            Integer totalRequirements,
            Integer requirementsMet,
            List<SkillGapItem> skills,
            String narrative,
            Integer coursesCounted) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    record SkillGapItem(
            String skillId,
            String label,
            String requiredLevel,
            Double requiredProficiency,
            Double currentLevel,
            Double gap,
            String classification,
            Double importance,
            Double priority) {
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
}
