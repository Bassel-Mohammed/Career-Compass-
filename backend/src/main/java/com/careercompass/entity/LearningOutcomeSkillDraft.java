package com.careercompass.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * A reviewable, course-scoped proposal.  AI output is stored here and remains invisible to
 * student vectors until an accepted/replaced/added subset is copied into a published map.
 */
@Entity
@Table(
        name = "learning_outcome_skill_drafts",
        uniqueConstraints = @UniqueConstraint(
                name = "uq_draft_skill_term", columnNames = {"outcome_id", "term"}),
        indexes = {
                @Index(name = "idx_draft_skills_outcome_decision",
                        columnList = "outcome_id,decision,draft_skill_id"),
                @Index(name = "idx_draft_skills_canonical",
                        columnList = "outcome_id,canonical_skill_id")
        })
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class LearningOutcomeSkillDraft {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "draft_skill_id")
    private Long draftSkillId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "outcome_id", nullable = false)
    private LearningOutcome outcome;

    @Column(name = "term", nullable = false, length = 200)
    private String term;

    @Column(name = "canonical_skill_id", length = 120)
    private String canonicalSkillId;

    @Column(name = "canonical_label", length = 200)
    private String canonicalLabel;

    @Column(name = "original_canonical_skill_id", length = 120)
    private String originalCanonicalSkillId;

    @Column(name = "original_canonical_label", length = 200)
    private String originalCanonicalLabel;

    @Column(name = "level", nullable = false, length = 30)
    private String level;

    @Builder.Default
    @Column(name = "weight", nullable = false, precision = 5, scale = 4)
    private BigDecimal weight = BigDecimal.ZERO;

    @Builder.Default
    @Column(name = "evidence_count", nullable = false)
    private Integer evidenceCount = 0;

    @Column(name = "evidence_json", columnDefinition = "TEXT")
    private String evidenceJson;

    @Column(name = "sources_json", columnDefinition = "TEXT")
    private String sourcesJson;

    @Column(name = "candidates_json", columnDefinition = "TEXT")
    private String candidatesJson;

    @Column(name = "match_method", length = 40)
    private String matchMethod;

    @Column(name = "match_score", precision = 5, scale = 4)
    private BigDecimal matchScore;

    @Column(name = "match_reason", columnDefinition = "TEXT")
    private String matchReason;

    @Builder.Default
    @Column(name = "ai_review_status", nullable = false, length = 30)
    private String aiReviewStatus = "no_match";

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "decision", nullable = false, length = 20)
    private SkillDraftDecision decision = SkillDraftDecision.PENDING;

    @Column(name = "note", length = 500)
    private String note;

    @Version
    @Builder.Default
    @Column(name = "row_version", nullable = false)
    private Long rowVersion = 0L;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        if (createdAt == null) {
            createdAt = now;
        }
        if (updatedAt == null) {
            updatedAt = now;
        }
        if (weight == null) {
            weight = BigDecimal.ZERO;
        }
        if (evidenceCount == null) {
            evidenceCount = 0;
        }
        if (aiReviewStatus == null) {
            aiReviewStatus = "no_match";
        }
        if (decision == null) {
            decision = SkillDraftDecision.PENDING;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
