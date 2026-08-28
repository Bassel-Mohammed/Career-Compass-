package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * Response from Module 3.
 *
 * <p>{@code classification} is "Strong" / "Moderate" / "Weak" per FR-JS-13. The wire contract
 * uses lower case; {@link com.careercompass.integration.ai.HttpDataAnalysisClient} normalises to
 * this title case at the boundary. Comparisons against these values are case-insensitive
 * everywhere on purpose — a silent case mismatch here produces an empty recommendation list
 * rather than an error, which is the worst kind of bug to find in a demo.
 *
 * <p>{@code explanation} is the one generated piece of this module (Section 5.3.3: an LLM
 * "explains the result but never produces the score"), supporting NFR-AI-04.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillGapAnalysisResponse {
    private List<SkillGapItemDto> skillGaps;
    private Integer overallReadinessPercent;
    /** Optional generated summary of the whole gap; null when not requested or unavailable. */
    private String narrative;

    /**
     * Classification counts split by demand band, keyed critical/important/useful, each carrying
     * strong, moderate, weak and total.
     *
     * <p>Kept rather than recomputed from {@code skillGaps} because the AI service counts these
     * over the rows it actually returned. Recomputing here would drift the moment either side
     * changes what it filters.
     */
    private Map<String, Map<String, Integer>> bandSummary;

    /**
     * Job postings this career path's requirements were derived from — the denominator behind
     * every {@code importance}. Null when the ontology carries no header; the arithmetic is
     * unaffected, only the evidence a UI can show is poorer.
     */
    private Integer sampleSize;

    /** ISO-8601 timestamp of when those postings were collected. */
    private String marketCapturedAt;

    /**
     * Transcript rows that fed the analysis.
     *
     * <p>Load-bearing rather than decorative: a requirement can read "no evidence" because the
     * student never studied it, or because the course that teaches it has no syllabus extracted
     * yet, and those are entirely different things to tell someone. Without these the dashboard
     * blames the student for the system's missing data.
     */
    private Integer coursesCounted;

    /** Of {@code coursesCounted}, how many rest on a synthetic syllabus rather than a real one. */
    private Integer syntheticCounted;

    private List<SkippedCourseDto> coursesSkipped;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SkippedCourseDto {
        private String courseCode;
        /** "no skill map" or "not passed". */
        private String reason;
        private String status;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SkillGapItemDto {
        private String skillId;
        private String skillName;
        private BigDecimal currentScore;
        private BigDecimal targetScore;
        private String classification; // "Strong" / "Moderate" / "Weak"
        private String explanation;

        /**
         * Share of this career path's postings that ask for the skill, as 0-100 per ADR-003.
         * The raw market demand, before any shortfall is applied.
         */
        private BigDecimal importancePercent;

        /**
         * {@code importance} bucketed by the AI service into "critical" / "important" / "useful".
         *
         * <p>Passed through rather than derived here on purpose: the thresholds live beside the
         * ontology that justifies them, and a second copy in Java would be the two disagreeing
         * about what "critical" means the first time either moved.
         */
        private String demandBand;

        /** Postings that asked for this skill — the numerator under {@code importancePercent}. */
        private Integer postingCount;

        /** "beginner" / "intermediate" / "advanced" — how deeply the market wants it. */
        private String requiredLevel;

        /** Taxonomy type: "knowledge", "skill", "tool" or "soft". */
        private String skillType;
        /**
         * Shortfall already weighted by market demand. Rank on this rather than on the raw gap:
         * a small shortfall in something every posting asks for matters more than a large
         * shortfall in something almost nobody does.
         */
        private BigDecimal priority;
        /** "grades", "grades+quizzes", "quizzes" or "transfer". */
        private String evidenceSource;
        /** Transcript courses whose extracted syllabi support this skill. */
        private List<CourseEvidenceDto> sourceCourses;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class CourseEvidenceDto {
        private String courseCode;
        private String courseName;
        private String grade;
        private String level;
    }
}
