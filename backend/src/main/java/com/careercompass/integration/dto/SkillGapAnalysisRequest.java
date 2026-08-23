package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Request to Module 3 (Skill-Gap Analysis, Section 5.3.3). Takes the already-computed skill
 * vector (from Module 2) rather than recomputing it, matching the report's description of
 * every downstream capability reading from the one Skill Vector artefact.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillGapAnalysisRequest {
    private Integer careerPathId;
    private List<SkillScoreDto> skillVector;
}
