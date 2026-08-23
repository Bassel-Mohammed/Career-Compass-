package com.careercompass.service;

import com.careercompass.dto.request.AvailabilitySlotRequest;
import com.careercompass.dto.request.ConsultationOutcomeRequest;
import com.careercompass.dto.request.UpdateAvailabilityRequest;
import com.careercompass.dto.response.*;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.mapper.ExpertMapper;
import com.careercompass.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Business Layer for an Expert's OWN actions (FR-EX-02..12).
 *
 * FR-EX-01 (login) lives in {@link AuthService}; account creation lives in
 * {@link ExpertAdminService} — same three-way split established for other actors
 * (registration/admin-creation vs. self-service vs. login), kept consistent here.
 *
 * <p><b>Skill-profile/course-recommendation access (FR-EX-07/08):</b> delegates directly to
 * {@link TranscriptService#getSkillDashboard} and
 * {@link CourseRecommendationService#listStoredRecommendations} — an Expert sees exactly the
 * same data a job seeker sees about themselves, gated by an appointment-existence check
 * ({@link AppointmentRepository#existsByExpert_ExpertIdAndJobSeeker_JobseekerId}) rather than a
 * separate read model, so there is exactly one source of truth for both.
 *
 * <p><b>FR-EX-10 (readiness evaluation) schema note:</b> the {@code appointments} table has no
 * dedicated "readiness" column — only {@code session_notes} and {@code feedback}. This service
 * treats {@code feedback} as also carrying the readiness evaluation (a free-text field covering
 * both FR-EX-09 and FR-EX-10), rather than inventing a structured field the schema doesn't
 * support. Flagged the same way the Increment 11/12 schema gaps were.
 */
@Service
@RequiredArgsConstructor
public class ExpertService {

    private final ExpertRepository expertRepository;
    private final ExpertStatusRepository expertStatusRepository;
    private final ExpertAvailabilityRepository expertAvailabilityRepository;
    private final AppointmentRepository appointmentRepository;
    private final AppointmentStatusRepository appointmentStatusRepository;
    private final ExpertMapper expertMapper;
    private final TranscriptService transcriptService;
    private final CourseRecommendationService courseRecommendationService;

    @Transactional(readOnly = true)
    public ExpertResponse getProfile(Integer expertId) {
        return expertMapper.toResponse(getOrThrow(expertId));
    }

    /** FR-EX-02: toggle "Active for consulting" / "Inactive for consulting". */
    @Transactional
    public ExpertResponse updateStatus(Integer expertId, boolean active) {
        Expert expert = getOrThrow(expertId);
        String statusName = active ? "Active" : "Inactive";
        ExpertStatus status = expertStatusRepository.findByStatusName(statusName)
                .orElseGet(() -> expertStatusRepository.save(ExpertStatus.builder().statusName(statusName).build()));
        expert.setStatus(status);
        return expertMapper.toResponse(expertRepository.save(expert));
    }

    /**
     * FR-EX-06: replace the expert's full weekly availability schedule. A full replace
     * (delete-then-recreate), not a merge — matches the "resubmit the whole schedule" pattern
     * already used for job postings (Increment 8) and academic records (Increment 10), and
     * avoids ambiguity about how to reconcile partial slot edits/removals.
     */
    @Transactional
    public List<AvailabilitySlotResponse> updateAvailability(Integer expertId, UpdateAvailabilityRequest request) {
        Expert expert = getOrThrow(expertId);

        expertAvailabilityRepository.deleteByExpert_ExpertId(expertId);

        List<ExpertAvailability> slots = request.getSlots().stream()
                .map(s -> ExpertAvailability.builder()
                        .expert(expert)
                        .dayOfWeek(s.getDayOfWeek().byteValue())
                        .startTime(s.getStartTime())
                        .endTime(s.getEndTime())
                        .build())
                .toList();
        List<ExpertAvailability> saved = expertAvailabilityRepository.saveAll(slots);

        return saved.stream()
                .map(s -> AvailabilitySlotResponse.builder()
                        .availabilityId(s.getAvailabilityId())
                        .dayOfWeek((int) s.getDayOfWeek())
                        .startTime(s.getStartTime())
                        .endTime(s.getEndTime())
                        .build())
                .toList();
    }

    /** FR-EX-05: upcoming scheduled sessions. */
    @Transactional(readOnly = true)
    public List<AppointmentResponse> getScheduledSessions(Integer expertId) {
        return appointmentRepository
                .findByExpert_ExpertIdAndAppointmentDateAfter(expertId, LocalDateTime.now()).stream()
                .map(this::toAppointmentResponse)
                .toList();
    }

    /** FR-EX-12: full consultation history. */
    @Transactional(readOnly = true)
    public List<AppointmentResponse> getConsultationHistory(Integer expertId) {
        return appointmentRepository.findByExpert_ExpertIdOrderByAppointmentDateDesc(expertId).stream()
                .map(this::toAppointmentResponse)
                .toList();
    }

    /** FR-EX-03: accept a consultation request. */
    @Transactional
    public AppointmentResponse acceptRequest(Integer expertId, Integer appointmentId) {
        return setAppointmentStatus(expertId, appointmentId, "Accepted");
    }

    /** FR-EX-04: reject a consultation request. */
    @Transactional
    public AppointmentResponse rejectRequest(Integer expertId, Integer appointmentId) {
        return setAppointmentStatus(expertId, appointmentId, "Rejected");
    }

    /** FR-EX-09/10/11: record session notes and feedback (see class Javadoc on FR-EX-10). */
    @Transactional
    public AppointmentResponse submitConsultationOutcome(
            Integer expertId, Integer appointmentId, ConsultationOutcomeRequest request) {
        Appointment appointment = getOwnedAppointmentOrThrow(expertId, appointmentId);
        if (request.getSessionNotes() != null) {
            appointment.setSessionNotes(request.getSessionNotes());
        }
        if (request.getFeedback() != null) {
            appointment.setFeedback(request.getFeedback());
        }
        return toAppointmentResponse(appointmentRepository.save(appointment));
    }

    /** FR-EX-07: view a job seeker's skill profile, gated by an existing consultation relationship. */
    @Transactional(readOnly = true)
    public SkillDashboardResponse viewJobSeekerSkillProfile(Integer expertId, Integer jobseekerId) {
        requireConsultationRelationship(expertId, jobseekerId);
        return transcriptService.getSkillDashboard(jobseekerId);
    }

    /** FR-EX-08: view a job seeker's recommended courses, same gating as above. */
    @Transactional(readOnly = true)
    public List<CourseRecommendationItem> viewJobSeekerRecommendedCourses(Integer expertId, Integer jobseekerId) {
        requireConsultationRelationship(expertId, jobseekerId);
        return courseRecommendationService.listStoredRecommendations(jobseekerId);
    }

    private void requireConsultationRelationship(Integer expertId, Integer jobseekerId) {
        if (!appointmentRepository.existsByExpert_ExpertIdAndJobSeeker_JobseekerId(expertId, jobseekerId)) {
            throw new UnauthorizedActionException(
                    "You may only view data for job seekers who have booked a session with you.");
        }
    }

    private AppointmentResponse setAppointmentStatus(Integer expertId, Integer appointmentId, String statusName) {
        Appointment appointment = getOwnedAppointmentOrThrow(expertId, appointmentId);
        AppointmentStatus status = appointmentStatusRepository.findByStatusName(statusName)
                .orElseGet(() -> appointmentStatusRepository.save(
                        AppointmentStatus.builder().statusName(statusName).build()));
        appointment.setStatus(status);
        return toAppointmentResponse(appointmentRepository.save(appointment));
    }

    private Appointment getOwnedAppointmentOrThrow(Integer expertId, Integer appointmentId) {
        Appointment appointment = appointmentRepository.findById(appointmentId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Appointment with id " + appointmentId + " not found."));

        if (!appointment.getExpert().getExpertId().equals(expertId)) {
            throw new UnauthorizedActionException("You do not have permission to modify this appointment.");
        }

        return appointment;
    }

    private Expert getOrThrow(Integer expertId) {
        return expertRepository.findById(expertId)
                .orElseThrow(() -> new ResourceNotFoundException("Expert with id " + expertId + " not found."));
    }

    private AppointmentResponse toAppointmentResponse(Appointment a) {
        return AppointmentResponse.builder()
                .appointmentId(a.getAppointmentId())
                .expertId(a.getExpert().getExpertId())
                .expertName(a.getExpert().getFirstName() + " " + a.getExpert().getLastName())
                .jobseekerId(a.getJobSeeker().getJobseekerId())
                .jobseekerName(a.getJobSeeker().getFirstName() + " " + a.getJobSeeker().getLastName())
                .appointmentDate(a.getAppointmentDate())
                .statusName(a.getStatus().getStatusName())
                .sessionNotes(a.getSessionNotes())
                .feedback(a.getFeedback())
                .createdAt(a.getCreatedAt())
                .build();
    }
}
