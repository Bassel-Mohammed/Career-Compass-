package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

/**
 * Maps to the `experts` table.
 * Expert / Mentor actor (Section 4.1.5 — FR-EX-xx).
 */
@Entity
@Table(name = "experts")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Expert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "expert_id")
    private Integer expertId;

    @Column(name = "first_name", nullable = false, length = 100)
    private String firstName;

    @Column(name = "last_name", nullable = false, length = 100)
    private String lastName;

    @Column(name = "email", nullable = false, unique = true, length = 255)
    private String email;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "study_field_id")
    private StudyField studyField;

    @Column(name = "field_starting_year", nullable = false)
    private Short fieldStartingYear;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "status_id", nullable = false)
    private ExpertStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by_admin_id")
    private Administrator createdByAdmin;
}
