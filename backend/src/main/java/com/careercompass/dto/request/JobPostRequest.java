package com.careercompass.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-EMP-07/09 (post / edit a job).
 */
@Getter
@Setter
public class JobPostRequest {

    @NotBlank(message = "Job title is required")
    @Size(max = 200)
    private String title;

    @NotBlank(message = "Job description is required")
    private String description;

    /** Free-text required skills as typed by the employer (FR-EMP-08). */
    private String requiredSkills;

    private Integer studyFieldId;
}
