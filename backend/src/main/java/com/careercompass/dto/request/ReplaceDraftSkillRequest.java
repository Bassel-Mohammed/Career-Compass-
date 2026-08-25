package com.careercompass.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/** Replaces an AI candidate with a reviewed canonical taxonomy identity. */
@Getter
@Setter
public class ReplaceDraftSkillRequest {

    @NotBlank(message = "Replacement skill id is required")
    @Size(max = 120)
    private String replacementSkillId;

    @Size(max = 500)
    private String note;

    @NotNull(message = "Expected row version is required")
    @PositiveOrZero
    private Long expectedRowVersion;

    @NotNull(message = "Expected draft revision is required")
    @PositiveOrZero
    private Long expectedDraftRevision;
}
