package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CareerPathResponse {
    private Integer careerPathId;
    private String title;
    private String careerPathCode;
    private String ontologyVersion;
    private String description;
    private List<StudyFieldResponse> studyFields;
    private LocalDateTime createdAt;
}
