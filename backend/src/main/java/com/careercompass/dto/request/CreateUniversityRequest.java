package com.careercompass.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for an Administrator to add a university.
 * Not tied to an explicit FR-SA-xx (the report doesn't list a standalone "create university"
 * requirement), but is a necessary prerequisite for FR-SA-03 (assign a university to a
 * Content Manager) and FR-CM-05 (Content Manager selects their university/field) — a
 * university has to exist before either of those can happen. Flagged in the increment doc.
 */
@Getter
@Setter
public class CreateUniversityRequest {

    @NotBlank(message = "University name is required")
    @Size(max = 200)
    private String universityName;
}
