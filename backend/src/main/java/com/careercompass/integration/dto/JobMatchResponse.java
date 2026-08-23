package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * Response from Module 6. `matchScore` maps directly onto `job_matches.match_score`.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class JobMatchResponse {
    private BigDecimal matchScore; // 0-100
    private String explanation;
}
