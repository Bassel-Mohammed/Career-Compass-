package com.careercompass.dto.request;

import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-SA-04 (update Content Manager account information). Partial-update style.
 */
@Getter
@Setter
public class UpdateContentManagerRequest {

    @Size(max = 100)
    private String firstName;

    @Size(max = 100)
    private String lastName;

    private Integer universityId;

    private Integer studyFieldId;
}
