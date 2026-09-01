package com.careercompass.dto.response;

import java.util.List;

import lombok.Builder;
import lombok.Getter;

/**
 * Auto-fill suggestion for the learning-outcome upload form, read back from the
 * PDF before upload. Every field is a suggestion: the content manager reviews
 * and can override, because the course code + catalog version pair remains the
 * qualified identity the workflow deduplicates and publishes against.
 */
@Getter
@Builder
public class LearningOutcomePreviewResponse {
    private String courseCode;
    private String courseName;
    private String description;
    private String contentSha256;
    private Integer totalTerms;
    private List<String> warnings;
}
