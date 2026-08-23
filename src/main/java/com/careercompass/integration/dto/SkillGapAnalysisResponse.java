package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * Response from Module 3. `classification` is "Strong" / "Moderate" / "Weak" per FR-JS-13.
 * `explanation` is the one LLM-generated piece of this module (Section 5.3.3: "An LLM then
 * writes a short, human-readable summary of numbers the system has already computed — it
 * explains the result but never produces the score"), directly supporting NFR-AI-04.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillGapAnalysisResponse {
    private List<SkillGapItemDto> skillGaps;
    private Integer overallReadinessPercent;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SkillGapItemDto {
        private String skillName;
        private BigDecimal currentScore;
        private BigDecimal targetScore;
        private String classification; // "Strong" / "Moderate" / "Weak"
        private String explanation;
    }
}
