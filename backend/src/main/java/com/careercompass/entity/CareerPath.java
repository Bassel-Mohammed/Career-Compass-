package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.Set;

/**
 * Maps to the `career_paths` table.
 * Managed by System Administrator (FR-SA-08/09/10); selected by Job Seeker (FR-JS-09).
 */
@Entity
@Table(name = "career_paths")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CareerPath {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "career_path_id")
    private Integer careerPathId;

    @Column(name = "title", nullable = false, length = 150)
    private String title;

    /** Stable cross-service identity. Nullable only while legacy title-keyed rows are backfilled. */
    @Column(name = "career_path_code", unique = true, length = 120)
    private String careerPathCode;

    /** Version of the approved career-path requirements/ontology this row is aligned with. */
    @Column(name = "ontology_version", length = 120)
    private String ontologyVersion;

    @Column(name = "description", columnDefinition = "TEXT")
    private String description;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by_admin_id")
    private Administrator createdByAdmin;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Builder.Default
    @ManyToMany
    @JoinTable(
            name = "career_path_study_fields",
            joinColumns = @JoinColumn(name = "career_path_id"),
            inverseJoinColumns = @JoinColumn(name = "study_field_id")
    )
    private Set<StudyField> studyFields = new HashSet<>();

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
