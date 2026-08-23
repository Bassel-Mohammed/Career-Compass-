package com.careercompass.dto.request;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-JS-17 (generate a quiz based on a recommended course).
 */
@Getter
@Setter
public class GenerateQuizRequest {

    @NotBlank(message = "Course name is required")
    private String courseName;

    @Min(1)
    @Max(20)
    private int questionCount = 5;
}
