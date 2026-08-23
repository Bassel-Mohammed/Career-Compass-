package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * A single job match for a job seeker (FR-JS-23) — the job seeker's side of Module 6
 * (Job Matching, Section 5.3.3).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class JobMatchResult {
    private Integer jobId;
    private String jobTitle;
    private String companyName;
    private BigDecimal matchScore; // 0-100
    private String explanation;
    private LocalDateTime matchedAt;
}
