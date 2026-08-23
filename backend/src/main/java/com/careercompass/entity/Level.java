package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

/**
 * Maps to the `levels` table.
 * Proficiency levels (e.g. Beginner/Intermediate/Advanced) used to grade a job seeker's
 * skill in `jobseeker_skills`.
 */
@Entity
@Table(name = "levels")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Level {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "level_id")
    private Integer levelId;

    @Column(name = "level_name", nullable = false, unique = true, length = 50)
    private String levelName;
}
