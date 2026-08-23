package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Response body for a job posting (FR-EMP-07 and browsing endpoints for job seekers).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class JobResponse {

    private Integer jobId;
    private Integer employerId;
    private String companyName; // denormalised for convenience — avoids a second frontend call

    private String title;
    private String description;
    private String requiredSkills;

    private Integer studyFieldId;
    private String studyFieldName;

    private List<String> skillNames; // from the job_skills many-to-many

    private Boolean isActive;
    private LocalDateTime postedAt;
}
