package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

/**
 * Maps to the `study_fields` table.
 * Created/managed by System Administrator (FR-SA-07).
 */
@Entity
@Table(name = "study_fields")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class StudyField {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "study_field_id")
    private Integer studyFieldId;

    @Column(name = "field_name", nullable = false, unique = true, length = 150)
    private String fieldName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by_admin_id")
    private Administrator createdByAdmin;
}
