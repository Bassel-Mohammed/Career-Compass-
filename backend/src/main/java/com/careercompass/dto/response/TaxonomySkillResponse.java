package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** Canonical taxonomy record shown in add/replace pickers. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TaxonomySkillResponse {
    private String skillId;
    private String label;
    private String skillType;
    private String source;
    private String description;
    private String taxonomyVersion;
}
