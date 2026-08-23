package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

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
         * Shortfall already weighted by market demand. Rank on this rather than on the raw gap:
         * a small shortfall in something every posting asks for matters more than a large
         * shortfall in something almost nobody does.
         */
        private BigDecimal priority;
    }
}
