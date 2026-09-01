package com.careercompass.repository;

import com.careercompass.entity.Appointment;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

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

    /**
     * FR-EX-05: what is still ahead of the expert — future-dated and not yet concluded.
     *
     * <p>Deliberately the exact complement of {@link #findHistoryForExpert}: an appointment
     * belongs to one list or the other, never both. The earlier pairing (everything after now
     * / everything, unfiltered) put every future request in both lists at once, so one screen
     * showed the same session twice with two different statuses.
     */
    @Query("""
            select a from Appointment a
             where a.expert.expertId = :expertId
               and a.appointmentDate > :now
               and a.status.statusName in ('Requested', 'Accepted')
             order by a.appointmentDate asc
            """)
    List<Appointment> findUpcomingForExpert(@Param("expertId") Integer expertId,
                                            @Param("now") LocalDateTime now);

    /**
     * FR-EX-12: what is behind the expert — the time has passed, or the request reached a
     * terminal state (rejected outright, or completed with a recorded outcome).
     */
    @Query("""
            select a from Appointment a
             where a.expert.expertId = :expertId
               and (a.appointmentDate <= :now or a.status.statusName in ('Rejected', 'Completed'))
             order by a.appointmentDate desc
            """)
    List<Appointment> findHistoryForExpert(@Param("expertId") Integer expertId,
                                           @Param("now") LocalDateTime now);

    /**
     * FR-JS-25 guard: is this expert's slot already taken?
     *
     * <p>A rejected request does not hold the slot — declining is exactly what frees it up
     * again — so only live requests and accepted sessions count as a clash.
     */
    @Query("""
            select count(a) > 0 from Appointment a
             where a.expert.expertId = :expertId
               and a.appointmentDate = :when
               and a.status.statusName <> 'Rejected'
            """)
    boolean isSlotTaken(@Param("expertId") Integer expertId, @Param("when") LocalDateTime when);
}
