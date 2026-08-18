package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * A single skill's computed score, as returned by Module 2 (deterministic scoring —
 * Section 5.3.1: "never depends on a language-model call"). `skillName` is used rather than
 * `skillId` for this cross-service contract, since the Python service reasons about skills
 * by name against its own ontology copy — the Java-side service layer resolves the name back
 * to a `Skill` entity id when persisting to `jobseeker_skills`.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillScoreDto {
    private String skillName;
    private BigDecimal score; // 0-100
}
