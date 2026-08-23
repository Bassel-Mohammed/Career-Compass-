package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Request to Module 6 (Job Matching, Section 5.3.3): scores one job seeker's skill vector
 * against ONE job's requirements. The Java side calls this per job (or the caller may batch
 * across a job seeker's candidate jobs) — job postings themselves live in the Java/MySQL
 * database (created by Employers), not in the Python service's own store, so Java supplies
 * the job's text directly rather than the Python service looking it up by id.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class JobMatchRequest {
    private List<SkillScoreDto> skillVector;
    private String jobTitle;
    private String jobDescription;
    private String jobRequiredSkills;
}
