package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * A single recommended course (FR-JS-15/16).
 *
 * `targetedSkillName` and `explanation` are only populated immediately after a fresh
 * generation call ({@code POST .../course-recommendations/generate}) — the `targetedSkillName`
 * and `explanation` are NOT columns in `courses_recommendations` (that table only has
 * `course_name` and `source_link`, per the corrected schema), so once recommendations are
 * simply read back later ({@code GET .../course-recommendations}), those two fields will be
 * null. Flagged explicitly in the increment doc as a schema limitation worth revisiting.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CourseRecommendationItem {
    private Integer recommendationId;
    private String courseName;
    private String sourceLink;
    private String targetedSkillName;
    private String explanation;
    private LocalDateTime recommendedAt;
}
