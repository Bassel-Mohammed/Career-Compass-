package com.careercompass.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
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

    @Size(max = 4000)
    private String description;

    @NotEmpty(message = "At least one study field must be linked to the career path")
    private List<Integer> studyFieldIds;
}
