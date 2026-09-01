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
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * Append-only snapshot header for one approved course-skill map.  Application code may only
 * transition its state from PUBLISHING to PUBLISHED or FAILED; a later review creates a new row.
 */
@Entity
@Table(
        name = "course_skill_map_versions",
        uniqueConstraints = @UniqueConstraint(
                name = "uq_course_map_scope_version",
                columnNames = {"institution_code", "catalog_version", "course_code", "map_version"}),
        indexes = {
                @Index(name = "idx_course_map_scope_state",
                        columnList = "institution_code,catalog_version,course_code,state,map_version"),
                @Index(name = "idx_course_map_source", columnList = "source_outcome_id,map_version")
        })
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CourseSkillMapVersion {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "map_id")
    private Long mapId;

    @Column(name = "institution_code", nullable = false, length = 120)
    private String institutionCode;

    @Column(name = "catalog_version", nullable = false, length = 120)
    private String catalogVersion;

    @Column(name = "course_code", nullable = false, length = 80)
    private String courseCode;

    @Column(name = "map_version", nullable = false)
    private Long mapVersion;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false, length = 20)
    private CourseSkillMapState state = CourseSkillMapState.PUBLISHING;

    @Column(name = "taxonomy_version", length = 120)
    private String taxonomyVersion;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "approved_by_content_manager_id")
    private ContentManager approvedByContentManager;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_outcome_id", nullable = false)
    private LearningOutcome sourceOutcome;

    @Column(name = "checksum", nullable = false, length = 64, columnDefinition = "CHAR(64)")
    private String checksum;

    @Column(name = "error", columnDefinition = "TEXT")
    private String error;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Column(name = "published_at")
    private LocalDateTime publishedAt;

    @Column(name = "failed_at")
    private LocalDateTime failedAt;

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        if (createdAt == null) {
            createdAt = now;
        }
        if (updatedAt == null) {
            updatedAt = now;
        }
        if (state == null) {
            state = CourseSkillMapState.PUBLISHING;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
