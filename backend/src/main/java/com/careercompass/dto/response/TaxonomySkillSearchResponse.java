package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/** Bounded taxonomy search result. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TaxonomySkillSearchResponse {
    private long total;
    private List<TaxonomySkillResponse> items;
}
