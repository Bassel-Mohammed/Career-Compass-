package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response from Module 2 — the Student Skill Vector (Section 5.3.1) for one job seeker's
 * chosen career path.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillVectorResponse {
    /** Taxonomy version reported by Python; nullable only for legacy/mock adapters. */
    private String taxonomyVersion;
    private List<SkillScoreDto> skills;
}
