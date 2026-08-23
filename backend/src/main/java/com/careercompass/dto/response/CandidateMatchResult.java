package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * A single matched candidate for a job posting (FR-EMP-11: matched job seekers;
 * FR-EMP-12: system-verified skill insights) — the employer's side of Module 6.
 *
 * `email` is included to directly support FR-EMP-13 (employer initiates communication with a
 * matched job seeker via their email address) — no in-app messaging exists, so the employer
 * needs the address to act on FR-EMP-13 outside the system.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CandidateMatchResult {
    private Integer jobseekerId;
    private String firstName;
    private String lastName;
    private String email;
    private BigDecimal matchScore; // 0-100
    private String explanation;
    private List<SkillInsight> skillInsights;
    private LocalDateTime matchedAt;

    /**
     * Lightweight skill/score pair — deliberately NOT the full SkillLevelResponse (which
     * includes a Strong/Moderate/Weak classification against a target). Computing that
     * classification requires running Module 3's skill-gap analysis per candidate per job
     * view, which isn't needed here: the report's FR-EMP-12 asks for "skill insights", which
     * this satisfies without the extra AI-service round-trips that a full gap analysis would
     * add for every candidate shown to an employer.
     */
    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SkillInsight {
        private String skillName;
        private BigDecimal score;
    }
}
