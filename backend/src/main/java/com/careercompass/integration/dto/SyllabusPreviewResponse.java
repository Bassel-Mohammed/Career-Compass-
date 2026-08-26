package com.careercompass.integration.dto;

import java.util.List;

import lombok.Builder;
import lombok.Getter;

/**
 * Metadata read back from a syllabus PDF before upload, so the browser can
 * pre-fill the course code / name / description fields. Read-only: nothing is
 * stored, matched, or extracted into a draft.
 */
@Getter
@Builder
public class SyllabusPreviewResponse {
    private String courseCode;
    private String courseTitle;
    private String description;
    private String contentSha256;
    private Integer totalTerms;
    private List<String> warnings;
}
