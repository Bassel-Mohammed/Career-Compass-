package com.careercompass.service;

import com.careercompass.dto.request.BookAppointmentRequest;
import com.careercompass.dto.response.AppointmentResponse;
import com.careercompass.dto.response.AvailabilitySlotResponse;
import com.careercompass.dto.response.MentorSummaryResponse;
import com.careercompass.entity.Appointment;
import com.careercompass.entity.AppointmentStatus;
import com.careercompass.entity.Expert;
import com.careercompass.entity.ExpertAvailability;
import com.careercompass.entity.JobSeeker;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.CourseGradeDto;
import com.careercompass.integration.dto.MentorMatchRequest;
import com.careercompass.integration.dto.MentorMatchResponse;
import com.careercompass.repository.AcademicRecordRepository;
import com.careercompass.repository.AppointmentRepository;
import com.careercompass.repository.AppointmentStatusRepository;
import com.careercompass.repository.ExpertAvailabilityRepository;
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.JobSeekerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.TextStyle;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Business Layer for a Job Seeker's mentor browsing and booking actions (FR-JS-24/25).
 * Appointment status transitions (accept/reject) are Expert-side actions, handled by
 * {@link ExpertService} — this service only ever creates a "Requested" appointment.
 */
@Service
@RequiredArgsConstructor
public class ConsultationService {

    private final JobSeekerRepository jobSeekerRepository;
    private final ExpertRepository expertRepository;
    private final AppointmentRepository appointmentRepository;
    private final AppointmentStatusRepository appointmentStatusRepository;
    private final ExpertAvailabilityRepository expertAvailabilityRepository;
    private final AcademicRecordRepository academicRecordRepository;
    private final TranscriptService transcriptService;
    private final DataAnalysisClient dataAnalysisClient;

    /** FR-JS-24: AI-ranked mentors. */
    @Transactional(readOnly = true)
    public List<MentorSummaryResponse> listAvailableMentors(Integer jobseekerId) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Job seeker with id " + jobseekerId + " not found."));

        if (jobSeeker.getCareerPath() == null) {
            throw new PrerequisiteNotMetException(
                    "Set your career path (FR-JS-09) before browsing AI-ranked mentors.");
        }

        List<Expert> activeMentors = expertRepository.findByStatus_StatusName("Active");
        if (activeMentors.isEmpty()) {
            return List.of();
        }

        List<CourseGradeDto> courses = academicRecordRepository.findByJobSeeker_JobseekerId(jobseekerId).stream()
                .map(r -> CourseGradeDto.builder()
                        .courseCode(r.getCourseCode())
                        .courseName(r.getCourseName())
                        .grade(r.getGrade())
                        .build())
                .toList();

        List<MentorMatchRequest.MentorDto> mentorDtos = activeMentors.stream()
                .map(e -> MentorMatchRequest.MentorDto.builder()
                        .mentorId(e.getExpertId().toString())
                        .studyField(e.getStudyField() != null ? e.getStudyField().getFieldName() : null)
                        .fieldStartingYear(e.getFieldStartingYear() != null ? e.getFieldStartingYear().intValue() : null)
                        .expertiseTerms(List.of())
                        .build())
                .toList();

        MentorMatchRequest request = MentorMatchRequest.builder()
                .careerPathName(jobSeeker.getCareerPath().getTitle())
                .courses(courses)
                .quizScores(transcriptService.latestQuizScoresBySkillId(jobseekerId))
                .mentors(mentorDtos)
                .limit(20)
                .build();

        MentorMatchResponse matchResponse = dataAnalysisClient.matchMentors(request);

        Map<Integer, Expert> expertById = activeMentors.stream()
                .collect(Collectors.toMap(Expert::getExpertId, Function.identity()));

        // One query for the whole page rather than one per mentor: the booking form needs each
        // mentor's slots to offer real times, and this list is short but never empty-handed.
        Map<Integer, List<AvailabilitySlotResponse>> slotsByExpert = expertAvailabilityRepository
                .findByExpert_ExpertIdIn(expertById.keySet()).stream()
                .collect(Collectors.groupingBy(
                        slot -> slot.getExpert().getExpertId(),
                        Collectors.mapping(ConsultationService::toSlotResponse, Collectors.toList())));

        return matchResponse.getItems().stream()
                .map(item -> {
                    Integer expertId = Integer.valueOf(item.getMentorId());
                    Expert e = expertById.get(expertId);
                    return MentorSummaryResponse.builder()
                            .expertId(e.getExpertId())
                            .firstName(e.getFirstName())
                            .lastName(e.getLastName())
                            .studyFieldName(e.getStudyField() != null ? e.getStudyField().getFieldName() : null)
                            .fieldStartingYear(e.getFieldStartingYear())
                            .matchScore(item.getScore())
                            .gapsAddressed(item.getGapsAddressed())
                            .matchReason(item.getExplanation())
                            .availability(slotsByExpert.getOrDefault(e.getExpertId(), List.of()).stream()
                                    .sorted(Comparator.comparing(AvailabilitySlotResponse::getDayOfWeek)
                                            .thenComparing(AvailabilitySlotResponse::getStartTime))
                                    .toList())
                            .build();
                })
                .toList();
    }

    private static AvailabilitySlotResponse toSlotResponse(ExpertAvailability slot) {
        return AvailabilitySlotResponse.builder()
                .availabilityId(slot.getAvailabilityId())
                .dayOfWeek((int) slot.getDayOfWeek())
                .startTime(slot.getStartTime())
                .endTime(slot.getEndTime())
                .build();
    }

    /** FR-JS-25: book a consultation session — always created with status "Requested". */
    @Transactional
    public AppointmentResponse bookSession(Integer jobseekerId, BookAppointmentRequest request) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Job seeker with id " + jobseekerId + " not found."));

        Expert expert = expertRepository.findById(request.getExpertId())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Expert with id " + request.getExpertId() + " not found."));

        requireWithinPublishedAvailability(expert, request.getAppointmentDate());

        if (appointmentRepository.isSlotTaken(expert.getExpertId(), request.getAppointmentDate())) {
            throw new DuplicateResourceException(
                    "That time has already been requested with this mentor. Pick another slot.");
        }

        AppointmentStatus requested = appointmentStatusRepository.findByStatusName("Requested")
                .orElseGet(() -> appointmentStatusRepository.save(
                        AppointmentStatus.builder().statusName("Requested").build()));

        Appointment appointment = Appointment.builder()
                .expert(expert)
                .jobSeeker(jobSeeker)
                .appointmentDate(request.getAppointmentDate())
                .status(requested)
                .build();
        appointment = appointmentRepository.save(appointment);

        return AppointmentResponse.builder()
                .appointmentId(appointment.getAppointmentId())
                .expertId(expert.getExpertId())
                .expertName(expert.getFirstName() + " " + expert.getLastName())
                .jobseekerId(jobSeeker.getJobseekerId())
                .jobseekerName(jobSeeker.getFirstName() + " " + jobSeeker.getLastName())
                .appointmentDate(appointment.getAppointmentDate())
                .statusName(requested.getStatusName())
                .createdAt(appointment.getCreatedAt())
                .build();
    }

    /**
     * FR-JS-25 / FR-EX-06: a session may only be requested inside a slot the mentor published.
     *
     * <p>Until this existed, {@code expert_availability} was write-only: mentors curated a
     * weekly schedule that nothing ever read, and students picked any instant they liked from
     * a free date-time field. The schedule page promised something the booking path did not
     * honour.
     *
     * <p>A mentor with no published slots is not bookable at all. That is the honest reading
     * of an empty schedule — "I have not said when I am free" is not the same as "any time
     * suits me" — and it matches what the availability screen tells the mentor.
     */
    private void requireWithinPublishedAvailability(Expert expert, LocalDateTime when) {
        // DayOfWeek.getValue() is 1=Monday..7=Sunday, the same convention the availability
        // editor stores and the frontend's DAY_NAMES renders.
        byte day = (byte) when.getDayOfWeek().getValue();
        List<ExpertAvailability> slots = expertAvailabilityRepository
                .findByExpert_ExpertIdAndDayOfWeek(expert.getExpertId(), day);

        if (slots.isEmpty()) {
            throw new PrerequisiteNotMetException(
                    expert.getFirstName() + " has not published any availability on "
                            + when.getDayOfWeek().getDisplayName(TextStyle.FULL, Locale.ENGLISH)
                            + ". Pick a day and time from their published schedule.");
        }

        LocalTime time = when.toLocalTime();
        // End is exclusive: a slot of 09:00–11:00 offers 09:00 and 10:59, not 11:00 itself,
        // so back-to-back slots cannot both claim the boundary minute.
        boolean covered = slots.stream()
                .anyMatch(s -> !time.isBefore(s.getStartTime()) && time.isBefore(s.getEndTime()));

        if (!covered) {
            String published = slots.stream()
                    .sorted(Comparator.comparing(ExpertAvailability::getStartTime))
                    .map(s -> s.getStartTime() + "–" + s.getEndTime())
                    .collect(Collectors.joining(", "));
            throw new PrerequisiteNotMetException(
                    expert.getFirstName() + " is available on "
                            + when.getDayOfWeek().getDisplayName(TextStyle.FULL, Locale.ENGLISH)
                            + " between " + published + ". Choose a time inside one of those slots.");
        }
    }

    /** View my own booked sessions (not a distinct FR, but a natural counterpart to FR-EX-05/12). */
    @Transactional(readOnly = true)
    public List<AppointmentResponse> listMyAppointments(Integer jobseekerId) {
        return appointmentRepository.findByJobSeeker_JobseekerIdOrderByAppointmentDateDesc(jobseekerId).stream()
                .map(a -> AppointmentResponse.builder()
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
                        .build())
                .toList();
    }
}
