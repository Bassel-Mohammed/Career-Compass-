package com.careercompass.service;

import com.careercompass.dto.request.BookAppointmentRequest;
import com.careercompass.dto.response.AppointmentResponse;
import com.careercompass.dto.response.MentorSummaryResponse;
import com.careercompass.entity.Appointment;
import com.careercompass.entity.AppointmentStatus;
import com.careercompass.entity.Expert;
import com.careercompass.entity.JobSeeker;
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
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.JobSeekerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
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
                            .build();
                })
                .toList();
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
