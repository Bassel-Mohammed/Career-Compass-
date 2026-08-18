package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Maps to the `job_seekers` table.
 * Job Seeker actor — the primary user (Section 4.1.1 — FR-JS-xx).
 */
@Entity
@Table(name = "job_seekers")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class JobSeeker {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "jobseeker_id")
    private Integer jobseekerId;

    @Column(name = "first_name", nullable = false, length = 100)
    private String firstName;

    @Column(name = "last_name", nullable = false, length = 100)
    private String lastName;

    @Column(name = "email", nullable = false, unique = true, length = 255)
    private String email;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "university_id")
    private University university;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "study_field_id")
    private StudyField studyField;

    // FR-JS-09: job seeker selects a desired career path
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "career_path_id")
    private CareerPath careerPath;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "last_login_at")
    private LocalDateTime lastLoginAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now();
        }
    }
}
