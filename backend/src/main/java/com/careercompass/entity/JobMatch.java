package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * Maps to the `job_matches` table.
 * Result of the AI job-matching module (FR-JS-23, FR-EMP-11) — `matchScore` is produced by
 * the Data Analyses Layer (embedding similarity) and persisted here by the backend.
 */
@Entity
@Table(name = "job_matches")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class JobMatch {

    @EmbeddedId
    private JobMatchId id;

    @ManyToOne(fetch = FetchType.LAZY)
    @MapsId("jobId")
    @JoinColumn(name = "job_id")
    private Job job;

    @ManyToOne(fetch = FetchType.LAZY)
    @MapsId("jobseekerId")
    @JoinColumn(name = "jobseeker_id")
    private JobSeeker jobSeeker;

    @Column(name = "match_score", nullable = false, precision = 5, scale = 2)
    private BigDecimal matchScore;

    @Column(name = "matched_at")
    private LocalDateTime matchedAt;

    @PrePersist
    protected void onCreate() {
        if (matchedAt == null) {
            matchedAt = LocalDateTime.now();
        }
    }
}
