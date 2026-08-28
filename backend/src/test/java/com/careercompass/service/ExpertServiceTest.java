package com.careercompass.service;

import com.careercompass.dto.request.ConsultationOutcomeRequest;
import com.careercompass.dto.response.AppointmentResponse;
import com.careercompass.dto.response.ExpertResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.mapper.ExpertMapper;
import com.careercompass.repository.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for ExpertService. Focused on: the appointment-ownership check (same pattern as
 * JobService/QuizService), and — most importantly — the FR-EX-07/08 consultation-relationship
 * gate that prevents an Expert from viewing a job seeker's data without a prior appointment.
 */
@ExtendWith(MockitoExtension.class)
class ExpertServiceTest {

    @Mock private ExpertRepository expertRepository;
    @Mock private ExpertStatusRepository expertStatusRepository;
    @Mock private ExpertAvailabilityRepository expertAvailabilityRepository;
    @Mock private AppointmentRepository appointmentRepository;
    @Mock private AppointmentStatusRepository appointmentStatusRepository;
    @Mock private ExpertMapper expertMapper;
    @Mock private TranscriptService transcriptService;
    @Mock private CourseRecommendationService courseRecommendationService;

    @InjectMocks
    private ExpertService expertService;

    // Purpose: Update Status - creates Status Lookup Row If Missing.
    @Test
    void updateStatus_createsStatusLookupRowIfMissing() {
        Expert expert = Expert.builder().expertId(1).build();
        when(expertRepository.findById(1)).thenReturn(Optional.of(expert));
        when(expertStatusRepository.findByStatusName("Active")).thenReturn(Optional.empty());
        when(expertStatusRepository.save(any(ExpertStatus.class))).thenAnswer(inv -> {
            ExpertStatus s = inv.getArgument(0);
            s.setStatusId(1);
            return s;
        });
        when(expertRepository.save(any(Expert.class))).thenAnswer(inv -> inv.getArgument(0));
        when(expertMapper.toResponse(any(Expert.class)))
                .thenReturn(ExpertResponse.builder().statusName("Active").build());

        ExpertResponse response = expertService.updateStatus(1, true);

        assertThat(response.getStatusName()).isEqualTo("Active");
        verify(expertStatusRepository).save(any(ExpertStatus.class));
    }

    // Purpose: Accept Request - throws Unauthorized When Expert Does Not Own Appointment.
    @Test
    void acceptRequest_throwsUnauthorizedWhenExpertDoesNotOwnAppointment() {
        Expert owner = Expert.builder().expertId(1).build();
        Appointment appointment = Appointment.builder().appointmentId(5).expert(owner).build();

        when(appointmentRepository.findById(5)).thenReturn(Optional.of(appointment));

        assertThatThrownBy(() -> expertService.acceptRequest(2, 5))
                .isInstanceOf(UnauthorizedActionException.class);
    }

    // Purpose: Submit Consultation Outcome - applies Only Provided Fields.
    @Test
    void submitConsultationOutcome_appliesOnlyProvidedFields() {
        Expert expert = Expert.builder().expertId(1).firstName("Dr").lastName("Smith").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(9).firstName("A").lastName("B").build();
        Appointment appointment = Appointment.builder()
                .appointmentId(5).expert(expert).jobSeeker(jobSeeker)
                .sessionNotes("Old notes").feedback("Old feedback")
                .status(AppointmentStatus.builder().statusName("Accepted").build())
                .build();

        when(appointmentRepository.findById(5)).thenReturn(Optional.of(appointment));
        when(appointmentStatusRepository.findByStatusName("Completed"))
                .thenReturn(Optional.of(AppointmentStatus.builder().statusName("Completed").build()));
        when(appointmentRepository.save(any(Appointment.class))).thenAnswer(inv -> inv.getArgument(0));

        ConsultationOutcomeRequest request = new ConsultationOutcomeRequest();
        request.setFeedback("New feedback covering readiness evaluation");
        // sessionNotes left null -> should stay unchanged

        AppointmentResponse response = expertService.submitConsultationOutcome(1, 5, request);

        assertThat(response.getFeedback()).isEqualTo("New feedback covering readiness evaluation");
        assertThat(response.getSessionNotes()).isEqualTo("Old notes");
        // Recording an outcome closes the session, which is what moves it out of the mentor's
        // upcoming list and into their history.
        assertThat(response.getStatusName()).isEqualTo("Completed");
    }

    // Purpose: View Job Seeker Skill Profile - throws When No Consultation Relationship Exists.
    @Test
    void viewJobSeekerSkillProfile_throwsWhenNoConsultationRelationshipExists() {
        when(appointmentRepository.existsByExpert_ExpertIdAndJobSeeker_JobseekerId(1, 9)).thenReturn(false);

        assertThatThrownBy(() -> expertService.viewJobSeekerSkillProfile(1, 9))
                .isInstanceOf(UnauthorizedActionException.class);

        verifyNoInteractions(transcriptService);
    }

    // Purpose: View Job Seeker Skill Profile - succeeds When Consultation Relationship Exists.
    @Test
    void viewJobSeekerSkillProfile_succeedsWhenConsultationRelationshipExists() {
        when(appointmentRepository.existsByExpert_ExpertIdAndJobSeeker_JobseekerId(1, 9)).thenReturn(true);
        when(transcriptService.getSkillDashboard(9))
                .thenReturn(com.careercompass.dto.response.SkillDashboardResponse.builder().jobseekerId(9).build());

        var dashboard = expertService.viewJobSeekerSkillProfile(1, 9);

        assertThat(dashboard.getJobseekerId()).isEqualTo(9);
    }

    // Purpose: Upcoming and Past are complements, never overlapping sets. A future request
    // that has not been answered yet belongs only to Upcoming; before this split it appeared
    // in both lists, and after an accept the two copies showed different statuses.
    @Test
    void scheduledAndHistory_queryDisjointSets() {
        Expert expert = Expert.builder().expertId(1).firstName("E").lastName("X").build();
        JobSeeker seeker = JobSeeker.builder().jobseekerId(9).firstName("A").lastName("B").build();
        AppointmentStatus requested = AppointmentStatus.builder().statusName("Requested").build();

        Appointment upcoming = Appointment.builder()
                .appointmentId(1).expert(expert).jobSeeker(seeker)
                .appointmentDate(LocalDateTime.now().plusDays(7)).status(requested).build();

        when(appointmentRepository.findUpcomingForExpert(eq(1), any())).thenReturn(List.of(upcoming));
        when(appointmentRepository.findHistoryForExpert(eq(1), any())).thenReturn(List.of());

        List<AppointmentResponse> scheduled = expertService.getScheduledSessions(1);
        List<AppointmentResponse> history = expertService.getConsultationHistory(1);

        assertThat(scheduled).extracting(AppointmentResponse::getAppointmentId).containsExactly(1);
        assertThat(history).isEmpty();
        // The service must delegate the filtering to the query rather than post-filtering an
        // unscoped "everything for this expert" fetch.
        verify(appointmentRepository, never()).findByExpert_ExpertIdOrderByAppointmentDateDesc(anyInt());
    }
}
