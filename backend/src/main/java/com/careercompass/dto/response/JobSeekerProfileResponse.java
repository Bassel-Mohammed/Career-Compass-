package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * Response body for FR-JS-06 (view personal profile).
 * Deliberately excludes `passwordHash` and any other sensitive/internal field from the
 * `JobSeeker` entity — this is the whole point of having a separate response DTO
 * (see our earlier discussion on why entities are not exposed directly through the API).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class JobSeekerProfileResponse {

    private Integer jobseekerId;
    private String firstName;
    private String lastName;
    private String email;

    private Integer universityId;
    private String universityName;

    private Integer studyFieldId;
    private String studyFieldName;

    private Integer careerPathId;
    private String careerPathTitle;

    private LocalDateTime createdAt;
    private LocalDateTime lastLoginAt;
}
