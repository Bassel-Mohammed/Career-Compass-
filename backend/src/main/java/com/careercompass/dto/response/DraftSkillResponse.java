package com.careercompass.dto.response;

import com.careercompass.entity.SkillDraftDecision;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/** Browser-facing form of an AI proposal plus the content manager's current decision. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DraftSkillResponse {
    private Long draftSkillId;
    private Integer outcomeId;
    private String term;
    private String canonicalSkillId;
    private String canonicalSkillLabel;
    private String originalCanonicalSkillId;
    private String originalCanonicalSkillLabel;
    private String level;
    private BigDecimal weight;
    private Integer evidenceCount;
    private List<String> sources;
    private List<Map<String, Object>> evidence;
    private List<DraftSkillCandidateResponse> candidates;
    private String matchMethod;
    private BigDecimal matchScore;
    private String matchReason;
    private String aiReviewStatus;
    private SkillDraftDecision decision;
    private String note;
    private Long rowVersion;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
