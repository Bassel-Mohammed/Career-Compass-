package com.careercompass.dto.response;

import com.careercompass.entity.LearningOutcomeExtractionStatus;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

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
    private String institutionCode;
    private String catalogVersion;
    private String courseCode;
    private String courseName;
    private String description;
    private String originalFilename;
    private String universityName;
    private String studyFieldName;
    private boolean deletedFromDisk;
    private LocalDateTime uploadedAt;
    private LocalDateTime updatedAt;
    private LearningOutcomeExtractionStatus extractionStatus;
    private String extractionError;
    private List<String> warnings;
    private String taxonomyVersion;
    private Long draftRevision;
    private Long courseMapVersion;
    private long totalSkills;
    private long pendingSkills;
    private LocalDateTime publishedAt;
}
