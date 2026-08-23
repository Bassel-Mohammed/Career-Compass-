package com.careercompass.dto.request;

import jakarta.validation.constraints.*;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for an Administrator to create an Expert account (FR-EX-01: "assigned by the
 * system administrator" — no self-registration, same pattern as Content Managers,
 * Increment 6). Not tied to an explicit FR-SA-xx (the report's FR-SA list only names Content
 * Manager account creation explicitly), but is the necessary counterpart — flagged the same
 * way CreateUniversityRequest was in Increment 6.
 */
@Getter
@Setter
public class CreateExpertRequest {

    @NotBlank @Size(max = 100)
    private String firstName;

    @NotBlank @Size(max = 100)
    private String lastName;

    @NotBlank @Email @Size(max = 255)
    private String email;

    @NotBlank @Size(min = 8, max = 100, message = "Password must be at least 8 characters")
    private String initialPassword;

    private Integer studyFieldId;

    @NotNull
    @Min(1950)
    private Short fieldStartingYear;
}
