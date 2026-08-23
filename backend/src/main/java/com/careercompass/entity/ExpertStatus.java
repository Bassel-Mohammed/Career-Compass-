package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

/**
 * Maps to the `expert_statuses` table.
 * Lookup table for expert consulting status (e.g. "Active", "Inactive" — FR-EX-02).
 */
@Entity
@Table(name = "expert_statuses")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ExpertStatus {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "status_id")
    private Integer statusId;

    @Column(name = "status_name", nullable = false, unique = true, length = 50)
    private String statusName;
}
