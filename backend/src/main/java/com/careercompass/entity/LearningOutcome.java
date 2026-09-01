package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Maps to the `learning_outcomes` table.
 * Course learning outcome PDFs uploaded by a Content Manager (FR-CM-04).
 * `filePath` / `isDeletedFromDisk` support NFR-PRIV-03 (raw PDFs deletable after extraction).
 */
@Entity
@Table(name = "learning_outcomes")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class LearningOutcome {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "outcome_id")
    private Integer outcomeId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "university_field_id", nullable = false)
    private UniversityStudyField universityField;

    @Column(name = "course_name", nullable = false, length = 200)
    private String courseName;

    @Column(name = "description", columnDefinition = "TEXT")
    private String description;

    @Column(name = "file_path", nullable = false, length = 500)
    private String filePath;

    @Column(name = "original_filename", nullable = false, length = 255)
    private String originalFilename;

    /** Stable institution identity used to qualify course codes across universities. */
    @Column(name = "institution_code", nullable = false, length = 120)
    private String institutionCode;

    /** Catalog edition in which {@link #courseCode} is defined. */
    @Column(name = "catalog_version", nullable = false, length = 120)
    private String catalogVersion;

    @Column(name = "course_code", nullable = false, length = 80)
    private String courseCode;

    /** SHA-256 of the uploaded bytes; nullable only for uploads created before Flyway V5. */
    @Column(name = "content_sha256", length = 64, columnDefinition = "CHAR(64)")
    private String contentSha256;

    @Column(name = "ai_extraction_id", unique = true, length = 120)
    private String aiExtractionId;

    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "extraction_status", nullable = false, length = 32)
    private LearningOutcomeExtractionStatus extractionStatus = LearningOutcomeExtractionStatus.UPLOADED;

    @Column(name = "extraction_error", columnDefinition = "TEXT")
    private String extractionError;

    /** JSON array kept private to persistence; response mappers expose a typed string list. */
    @Column(name = "extraction_warnings_json", columnDefinition = "TEXT")
    private String extractionWarningsJson;

    @Column(name = "taxonomy_version", length = 120)
    private String taxonomyVersion;

    /** Aggregate compare-and-swap token advanced whenever draft skills change. */
    @Builder.Default
    @Column(name = "draft_revision", nullable = false)
    private Long draftRevision = 0L;

    /** Last successfully published append-only map version, or zero when never published. */
    @Builder.Default
    @Column(name = "course_map_version", nullable = false)
    private Long courseMapVersion = 0L;

    @Builder.Default
    @Column(name = "is_deleted_from_disk", nullable = false)
    private Boolean isDeletedFromDisk = false;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "uploaded_by_content_manager_id")
    private ContentManager uploadedByContentManager;

    @Column(name = "uploaded_at")
    private LocalDateTime uploadedAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Column(name = "published_at")
    private LocalDateTime publishedAt;

    @PrePersist
    protected void onCreate() {
        if (uploadedAt == null) {
            uploadedAt = LocalDateTime.now();
        }
        if (updatedAt == null) {
            updatedAt = uploadedAt;
        }
        if (extractionStatus == null) {
            extractionStatus = LearningOutcomeExtractionStatus.UPLOADED;
        }
        if (draftRevision == null) {
            draftRevision = 0L;
        }
        if (courseMapVersion == null) {
            courseMapVersion = 0L;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
