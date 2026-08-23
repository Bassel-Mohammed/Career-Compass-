package com.careercompass.dto.request;

import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-EMP-06 (update company profile information). Partial-update style,
 * consistent with UpdateJobSeekerProfileRequest (Increment 4) and UpdateCareerPathRequest
 * (Increment 6). Email/password intentionally excluded — same reasoning as the job seeker
 * profile update (dedicated, more carefully-guarded endpoints, not yet built).
 */
@Getter
@Setter
public class UpdateEmployerProfileRequest {

    @Size(max = 200)
    private String companyName;

    @Size(max = 150)
    private String industry;

    @Size(max = 2000)
    private String companyDescription;
}
