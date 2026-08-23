package com.careercompass.repository;

import com.careercompass.entity.Appointment;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Data Access Layer for `appointments`.
 * Supports FR-JS-25 (book session), FR-EX-03/04/05/12 (accept/reject/view sessions/history).
 */
public interface AppointmentRepository extends JpaRepository<Appointment, Integer> {

    List<Appointment> findByJobSeeker_JobseekerIdOrderByAppointmentDateDesc(Integer jobseekerId);

    List<Appointment> findByExpert_ExpertIdOrderByAppointmentDateDesc(Integer expertId);

    List<Appointment> findByExpert_ExpertIdAndAppointmentDateAfter(Integer expertId, LocalDateTime after);

    List<Appointment> findByExpert_ExpertIdAndStatus_StatusName(Integer expertId, String statusName);

    /**
     * Ownership check for FR-EX-07/08 (expert views a job seeker's skill profile/recommended
     * courses): an expert may only view a job seeker's data if a consultation relationship
     * (any status) already exists between them.
     */
    boolean existsByExpert_ExpertIdAndJobSeeker_JobseekerId(Integer expertId, Integer jobseekerId);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
