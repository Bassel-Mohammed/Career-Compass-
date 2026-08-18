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

    @Builder.Default
    @Column(name = "is_deleted_from_disk", nullable = false)
    private Boolean isDeletedFromDisk = false;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "uploaded_by_content_manager_id")
    private ContentManager uploadedByContentManager;

    @Column(name = "uploaded_at")
    private LocalDateTime uploadedAt;

    @PrePersist
    protected void onCreate() {
        if (uploadedAt == null) {
            uploadedAt = LocalDateTime.now();
        }
    }
}
