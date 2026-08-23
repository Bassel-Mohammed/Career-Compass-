package com.careercompass.dto.request;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-SA-02/03 (admin creates a Content Manager account and assigns their
 * university). Per FR-CM-01 ("log in using a registered password... by the system
 * administrator"), the Administrator sets the initial password directly — there is no
 * self-registration flow for this actor (see AuthService's Javadoc for the reasoning).
 */
@Getter
@Setter
public class CreateContentManagerRequest {

    @NotBlank
    @Size(max = 100)
    private String firstName;

    @NotBlank
    @Size(max = 100)
    private String lastName;

    @NotBlank
    @Email
    @Size(max = 255)
    private String email;

    @NotBlank
    @Size(min = 8, max = 100, message = "Password must be at least 8 characters")
    private String initialPassword;

    @NotNull(message = "University is required")
    private Integer universityId;

    /** Study field the Content Manager teaches in (FR-CM-05); optional at creation time. */
    private Integer studyFieldId;
}
