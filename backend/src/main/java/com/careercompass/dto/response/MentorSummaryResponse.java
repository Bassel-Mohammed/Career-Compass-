package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import java.math.BigDecimal;

/**
 * A mentor/expert as browsable by a job seeker (FR-JS-24).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MentorSummaryResponse {
    private Integer expertId;
    private String firstName;
    private String lastName;
    private String studyFieldName;
    private Short fieldStartingYear;
    private BigDecimal matchScore;
    private Integer gapsAddressed;
    private String matchReason;
}
