package com.careercompass.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-SA-07 (add a study field to the system).
 */
@Getter
@Setter
public class CreateStudyFieldRequest {

    @NotBlank(message = "Field name is required")
    @Size(max = 150)
    private String fieldName;
}
