package com.careercompass.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * Request body for FR-SA-08 (create a career path title, associated with study field(s)).
 */
@Getter
@Setter
public class CreateCareerPathRequest {

    @NotBlank(message = "Career path title is required")
    @Size(max = 150)
    private String title;

    /**
     * Optional reviewed cross-service identity. When omitted Java creates an opaque code; it is
     * never inferred from the mutable title.
     */
    @Size(max = 120)
    @Pattern(regexp = "[A-Za-z0-9][A-Za-z0-9._:-]*",
            message = "careerPathCode contains unsupported characters")
    private String careerPathCode;

    @Size(max = 120)
    private String ontologyVersion;

    @Size(max = 4000)
    private String description;

    @NotEmpty(message = "At least one study field must be linked to the career path")
    private List<Integer> studyFieldIds;
}
