package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

/**
 * Maps to the `appointment_statuses` table.
 * Lookup table for consultation status (e.g. "Requested", "Accepted", "Rejected",
 * "Completed" — FR-EX-03/04).
 */
@Entity
@Table(name = "appointment_statuses")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AppointmentStatus {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "status_id")
    private Integer statusId;

    @Column(name = "status_name", nullable = false, unique = true, length = 50)
    private String statusName;
}
