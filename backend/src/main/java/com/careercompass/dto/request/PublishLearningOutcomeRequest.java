package com.careercompass.dto.request;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import lombok.Getter;
import lombok.Setter;

/** Compare-and-swap token required before approving and publishing the reviewed map. */
@Getter
@Setter
public class PublishLearningOutcomeRequest {

    @NotNull(message = "Expected draft revision is required")
    @PositiveOrZero
    private Long expectedDraftRevision;
}
