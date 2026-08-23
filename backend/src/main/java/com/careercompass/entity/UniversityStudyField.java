package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;

/**
 * Maps to the `university_study_fields` table.
 * A specific study field offered by a specific university (with degree level & duration).
 */
@Entity
@Table(name = "university_study_fields",
        uniqueConstraints = @UniqueConstraint(name = "uq_university_field",
                columnNames = {"university_id", "study_field_id"}))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UniversityStudyField {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "university_field_id")
    private Integer universityFieldId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "university_id", nullable = false)
    private University university;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "study_field_id", nullable = false)
    private StudyField studyField;

    @Column(name = "degree_level", length = 50)
    private String degreeLevel;

    @Column(name = "duration_years", precision = 3, scale = 1)
    private BigDecimal durationYears;
}
