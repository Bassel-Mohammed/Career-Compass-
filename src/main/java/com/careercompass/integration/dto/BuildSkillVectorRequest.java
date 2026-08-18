package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Request to the Data Analyses service's Module 2 (Skill Vector construction).
 * `jobseekerId` is included for logging/traceability on the Python side, not because the
 * Python service owns any job-seeker data itself.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BuildSkillVectorRequest {
    private Integer jobseekerId;
    private Integer careerPathId;
    private List<CourseGradeDto> courses;
}
