package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * Request to Module 4 (Course Recommendation, Section 5.3.3).
 *
 * <p>Like the gap, this sends the confirmed courses and lets the AI service derive the gaps it
 * should recommend against. Java previously sent a list of weak skill <em>names</em>, which
 * could not be resolved back to the catalog's canonical skills and silently produced nothing
 * whenever the label did not match.
 *
 * <p>Recommendations are retrieved from a real catalog and re-ranked, never generated
 * (NFR-AI-05), so every returned course exists and carries a working link.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CourseRecommendationRequest {
    private String careerPathName;
    private List<CourseGradeDto> courses;
    private Map<String, BigDecimal> quizScores;
    /** Maximum courses to return overall. The AI service caps this at 50. */
    private Integer limit;
    /** Optional: restrict to one canonical skill id. */
    private String skillId;
}
