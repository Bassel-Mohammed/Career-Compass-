package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * A single skill's score/level within a {@link SkillDashboardResponse}
 * (FR-JS-13: classify Strong/Weak; Figure 5.4.6/5.4.7 in the report).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillLevelResponse {

    /** Java's local {@code skills} table id. Meaningless to the AI service. */
    private Integer skillId;

    /**
     * The AI service's canonical skill id. This is what a quiz request must carry, so the
     * dashboard has to surface it — otherwise the UI has only a label, and resolving a label
     * back to a skill is the ambiguity this whole identifier exists to remove.
     */
    private String canonicalSkillId;

    private String skillName;

    /** 0-100 current score. */
    private BigDecimal score;

    /** "Strong" / "Moderate" / "Weak" — derived from score vs. career-path target. */
    private String classification;

    /**
     * Short, human-readable explanation of why this score was produced (NFR-AI-04).
     * Optional — may be null when the source data doesn't provide one.
     */
    private String explanation;
}
