package com.careercompass.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import lombok.Getter;
import lombok.Setter;

/** Soft-deletes a draft skill by recording the REMOVED decision. */
@Getter
@Setter
public class DeleteDraftSkillRequest {

    @NotNull(message = "Expected row version is required")
    @PositiveOrZero
    private Long expectedRowVersion;

    @NotNull(message = "Expected draft revision is required")
    @PositiveOrZero
    private Long expectedDraftRevision;
}
