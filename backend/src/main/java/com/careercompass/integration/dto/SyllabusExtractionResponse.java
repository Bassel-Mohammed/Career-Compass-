package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * Durable Java-side view of one asynchronous syllabus extraction proposal.
 *
 * <p>Scores remain on the AI contract's {@code 0.0..1.0} scale. They are audit signals, not
 * percentages and not automatic approval decisions.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SyllabusExtractionResponse {
    private String extractionId;
    private String status;
    private String courseCode;
    private String contentSha256;
    private boolean degraded;
    private Progress progress;
    private Result result;
    private List<String> warnings;
    private String error;
    private String createdAt;
    private String finishedAt;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Progress {
        private String stage;
        private Integer termsTotal;
        private Integer termsResolved;
        private BigDecimal elapsedSeconds;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Result {
        private String courseCode;
        private Integer totalSkills;
        private String taxonomyVersion;
        private List<ExtractedSkill> skills;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ExtractedSkill {
        private String term;
        private CanonicalSkill canonical;
        private String level;
        private BigDecimal weight;
        private Integer evidenceCount;
        private List<String> sources;
        private List<Map<String, Object>> evidence;
        private Match match;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class CanonicalSkill {
        private String id;
        private String label;
        private String taxonomy;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Match {
        private String originalTerm;
        private String canonicalId;
        private String canonicalLabel;
        private String taxonomy;
        private String taxonomyVersion;
        private String matchMethod;
        private BigDecimal matchScore;
        private String reviewStatus;
        private String reason;
        private List<Candidate> candidates;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Candidate {
        private String id;
        private String label;
        private BigDecimal score;
    }
}
