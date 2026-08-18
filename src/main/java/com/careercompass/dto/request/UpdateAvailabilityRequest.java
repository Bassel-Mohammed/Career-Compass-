package com.careercompass.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * Request body for FR-EX-06 (update availability schedule). Replaces the expert's full weekly
 * schedule — see ExpertService's Javadoc for why this is a full replace, not a merge.
 */
@Getter
@Setter
public class UpdateAvailabilityRequest {

    @NotEmpty(message = "At least one availability slot is required")
    @Valid
    private List<AvailabilitySlotRequest> slots;
}
