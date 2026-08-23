package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * Response body for Content Manager account views (FR-SA-02..06). Excludes `passwordHash`.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ContentManagerResponse {
    private Integer contentManagerId;
    private String firstName;
    private String lastName;
    private String email;

    private Integer universityId;
    private String universityName;

    private Integer studyFieldId;
    private String studyFieldName;

    private Boolean isActive;
    private LocalDateTime createdAt;
}
