package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A single (course name, grade) pair sent to the Data Analyses service as input to
 * Module 2 (Skill Vector construction, Section 5.3.3). Mirrors `academic_records` fields,
 * but deliberately kept as its own DTO rather than reusing the entity — this is the
 * cross-service contract, not persistence, and the two should be free to evolve independently
 * (see our earlier discussion on why a mismatch here should only ever touch this package).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CourseGradeDto {
    private String courseCode;
    private String courseName;
    private String grade;
}
