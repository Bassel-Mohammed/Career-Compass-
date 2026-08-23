package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A single recommended course, as returned by Module 4. Retrieved from the curated ChromaDB
 * catalog (NFR-AI-05: the system cannot invent non-existent courses), then re-ranked/explained
 * by an LLM. Maps directly onto `courses_recommendations` (course_name, source_link) when
 * persisted by JobSeekerAiService (a later increment).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RecommendedCourseDto {
    private String courseName;
    private String sourceLink;
    private String targetedSkillName;
    private String explanation;
}
