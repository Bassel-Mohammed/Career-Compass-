package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** One confirmed transcript course that contributed evidence for a dashboard skill. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillCourseEvidenceResponse {
    private String courseCode;
    private String courseName;
    private String grade;
    /** How deeply the syllabus teaches the skill: beginner, intermediate or advanced. */
    private String level;
}
