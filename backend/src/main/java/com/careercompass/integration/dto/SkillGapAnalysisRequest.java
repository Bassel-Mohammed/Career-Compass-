package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * Request to Module 3 (Skill-Gap Analysis, Section 5.3.3).
 *
 * <p>This carries the confirmed courses and quiz evidence rather than a pre-computed vector.
 * That is deliberate: the AI service recomputes the vector from the same inputs so that the gap
 * can never be built from a vector that disagrees with the one Module 2 would produce. Two
 * services independently computing "the" skill vector is how the numbers on a dashboard and the
 * numbers behind a recommendation drift apart.
 *
 * <p>{@code careerPathName} is the path's <em>name</em>, not Java's numeric id — neither service
 * owns the other's identifiers. An unknown name comes back as a controlled error listing the
 * names the AI service does know, rather than an empty gap that looks like a perfect student.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillGapAnalysisRequest {
    private String careerPathName;
    private List<CourseGradeDto> courses;
    private Map<String, BigDecimal> quizScores;
    /** Ask the AI service for its generated summary. Costs an LLM call; the gap is complete without it. */
    private boolean includeNarrative;
}
