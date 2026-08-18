package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

/**
 * Maps to the `skills` table.
 * Part of the skills ontology (Section 5.3.2) that underpins the Student Skill Vector.
 */
@Entity
@Table(name = "skills")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Skill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "skill_id")
    private Integer skillId;

    @Column(name = "skill_name", nullable = false, unique = true, length = 150)
    private String skillName;
}
