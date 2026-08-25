package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** Confirmation that Python atomically installed an approved course-map version. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PublishCourseMapResponse {
    private String courseMapVersion;
    private String courseKey;
    private String courseCode;
    private String taxonomyVersion;
    private Integer totalSkills;
    private String contentSha256;
    private String publishedAt;
    private boolean idempotent;
}
