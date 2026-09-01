package com.careercompass.dto.request;

import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * Request body for FR-SA-09 (update a career path title). Partial-update style.
 */
@Getter
@Setter
public class UpdateCareerPathRequest {

    @Size(max = 150)
    private String title;

    @Size(max = 4000)
    private String description;

    /** Updates provenance without changing the career path's stable code. */
    @Size(max = 120)
    private String ontologyVersion;

    /** If provided, replaces the full set of linked study fields. */
    private List<Integer> studyFieldIds;
}
