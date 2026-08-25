package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** One canonical taxonomy record returned for a content-manager picker. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TaxonomySkillSuggestion {
    private String skillId;
    private String label;
    private String skillType;
    private String source;
    private String description;
    private String taxonomyVersion;
}
