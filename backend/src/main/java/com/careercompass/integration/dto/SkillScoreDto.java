package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * One skill's score in the Student Skill Vector (Module 2).
 *
 * <p>{@code skillId} is the canonical identity and {@code skillName} is display text. They are
 * deliberately separate: the AI service's taxonomy renames labels between versions, and a label
 * is not unique — two paths can both call something "testing". Anything that needs to join
 * (quiz write-back, gap requirements, persistence) must key on {@code skillId}. Treating the
 * label as identity is what made the old course-name-equals-skill-name write-back unsound.
 *
 * <p>{@code score} is a Java-side percentage in {@code 0..100}. The wire contract carries
 * {@code 0.0..1.0}; {@code HttpDataAnalysisClient} converts at the boundary and nowhere else.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillScoreDto {
    private String skillId;
    private String skillName;
    private BigDecimal score; // 0-100 (converted from the contract's 0.0-1.0 at the adapter)
}
