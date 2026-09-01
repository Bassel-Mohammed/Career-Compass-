package com.careercompass.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** Immutable skill value copied from a reviewed draft into a versioned publication. */
@Entity
@Table(
        name = "course_skill_map_items",
        uniqueConstraints = @UniqueConstraint(
                name = "uq_course_map_canonical_skill", columnNames = {"map_id", "canonical_skill_id"}),
        indexes = @Index(name = "idx_course_map_items_canonical", columnList = "canonical_skill_id"))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CourseSkillMapItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "map_item_id")
    private Long mapItemId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "map_id", nullable = false)
    private CourseSkillMapVersion mapVersion;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "source_draft_skill_id")
    private LearningOutcomeSkillDraft sourceDraftSkill;

    @Column(name = "term", nullable = false, length = 200)
    private String term;

    @Column(name = "canonical_skill_id", nullable = false, length = 120)
    private String canonicalSkillId;

    @Column(name = "canonical_label", nullable = false, length = 200)
    private String canonicalLabel;

    @Column(name = "level", nullable = false, length = 30)
    private String level;

    @Column(name = "weight", nullable = false, precision = 5, scale = 4)
    private BigDecimal weight;

    @Builder.Default
    @Column(name = "evidence_count", nullable = false)
    private Integer evidenceCount = 0;

    /** Immutable JSON array copied verbatim from the reviewed draft at publication time. */
    @Column(name = "sources_json", columnDefinition = "TEXT")
    private String sourcesJson;

    /** Immutable evidence objects used to reproduce and audit the publication checksum. */
    @Column(name = "evidence_json", columnDefinition = "TEXT")
    private String evidenceJson;

    @Column(name = "decision_note", length = 500)
    private String decisionNote;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
        if (evidenceCount == null) {
            evidenceCount = 0;
        }
    }
}
