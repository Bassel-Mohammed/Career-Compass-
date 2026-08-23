package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Request to Module 4 (Course Recommendation, Section 5.3.3): top-k semantic search over the
 * ChromaDB course catalog, filtered by the given weak skills and career path.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CourseRecommendationRequest {
    private Integer careerPathId;
    private List<String> weakSkillNames;
}
