package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * Complete approved course map sent to Python as one idempotent replacement.
 * Partial/delta publication is intentionally unsupported: a removed skill must disappear from
 * the derived index rather than survive because one service missed a delete event.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PublishCourseMapRequest {
    private String courseMapVersion;
    private String institutionCode;
    private String catalogVersion;
    private String courseCode;
    private String sourceOutcomeId;
    private String taxonomyVersion;
    private List<ApprovedSkill> skills;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ApprovedSkill {
        private String skillId;
        private String skillLabel;
        private String term;
        private String level;
        private BigDecimal weight;
        private Integer evidenceCount;
        private List<String> sources;
        private List<Map<String, Object>> evidence;
    }
}
