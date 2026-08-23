package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * Response body for FR-JS-14/21 (skill profile dashboard — bar chart of strengths/weaknesses).
 * `skills` is ordered weakest-first by the service layer so the frontend can render it
 * directly without re-sorting (mirrors the report's UI mockup, Figure 5.4.6).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillDashboardResponse {

    private Integer jobseekerId;
    private String careerPathTitle;

    /** 0-100 overall readiness score for the selected career path. */
    private Integer overallReadinessPercent;

    private List<SkillLevelResponse> skills;

    /**
     * True if this dashboard was built from quiz results (FR-JS-20/21);
     * false if it fell back to grade-based scoring only (FR-JS-22).
     */
    private boolean basedOnQuizResults;
}
