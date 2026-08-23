package com.careercompass.dto.request;

import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-CM-05 (Content Manager selects the study field they teach in).
 * Separate from admin's UpdateContentManagerRequest (Increment 6) — this is the Content
 * Manager acting on their own account, not an admin acting on someone else's.
 */
@Getter
@Setter
public class SelectStudyFieldRequest {

    @NotNull(message = "Study field is required")
    private Integer studyFieldId;
}
