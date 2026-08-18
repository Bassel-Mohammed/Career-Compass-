package com.careercompass.repository;

import com.careercompass.entity.AppointmentStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `appointment_statuses` (lookup table, e.g.
 * "Requested"/"Accepted"/"Rejected"/"Completed").
 */
public interface AppointmentStatusRepository extends JpaRepository<AppointmentStatus, Integer> {

    Optional<AppointmentStatus> findByStatusName(String statusName);
}
