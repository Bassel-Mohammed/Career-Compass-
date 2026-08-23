package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * Response body for viewing/updating an employer's company profile (FR-EMP-05/06).
 * Excludes `passwordHash`.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EmployerProfileResponse {

    private Integer employerId;
    private String companyName;
    private String industry;
    private String email;
    private String companyDescription;
    private LocalDateTime createdAt;
}
