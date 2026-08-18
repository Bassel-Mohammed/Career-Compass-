package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Maps to the `academic_records` table.
 * Extracted course/grade pairs from an uploaded transcript PDF (FR-JS-11, FR-JS-12).
 */
@Entity
@Table(name = "academic_records")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AcademicRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "record_id")
    private Integer recordId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "jobseeker_id", nullable = false)
    private JobSeeker jobSeeker;

    @Column(name = "course_name", nullable = false, length = 200)
    private String courseName;

    @Column(name = "grade", nullable = false, length = 10)
    private String grade;

    @Column(name = "extracted_at")
    private LocalDateTime extractedAt;

    @PrePersist
    protected void onCreate() {
        if (extractedAt == null) {
            extractedAt = LocalDateTime.now();
        }
    }
}
