package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * Response body for an uploaded learning outcome (FR-CM-04). Excludes `filePath` — that's an
 * internal storage detail, not something the frontend needs (same entity-vs-DTO boundary
 * principle used throughout this project).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class LearningOutcomeResponse {
    private Integer outcomeId;
    private String courseName;
    private String description;
    private String originalFilename;
    private String universityName;
    private String studyFieldName;
    private boolean deletedFromDisk;
    private LocalDateTime uploadedAt;
}
