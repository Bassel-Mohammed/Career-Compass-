package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Response body for Expert account views. Excludes `passwordHash`.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ExpertResponse {
    private Integer expertId;
    private String firstName;
    private String lastName;
    private String email;
    private Integer studyFieldId;
    private String studyFieldName;
    private Short fieldStartingYear;
    private String statusName; // "Active" / "Inactive" for consulting (FR-EX-02)
}
