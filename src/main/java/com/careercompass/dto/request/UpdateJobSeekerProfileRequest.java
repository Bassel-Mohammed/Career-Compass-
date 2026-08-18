package com.careercompass.dto.request;

import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-JS-07 (update personal profile).
 * All fields optional — only non-null fields are applied (partial update).
 * Email/password changes are intentionally NOT included here; those should go through
 * dedicated, more carefully-guarded endpoints once the Security Layer is built.
 */
@Getter
@Setter
public class UpdateJobSeekerProfileRequest {

    @Size(max = 100)
    private String firstName;

    @Size(max = 100)
    private String lastName;

    private Integer universityId;

    private Integer studyFieldId;

    /** FR-JS-09: job seeker selects/changes their desired career path. */
    private Integer careerPathId;
}
