package com.careercompass.service;

import com.careercompass.dto.request.BookAppointmentRequest;
import com.careercompass.dto.response.AppointmentResponse;
import com.careercompass.dto.response.MentorSummaryResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.repository.AppointmentRepository;
import com.careercompass.repository.AppointmentStatusRepository;
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.JobSeekerRepository;
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
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ConsultationServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private ExpertRepository expertRepository;
    @Mock private AppointmentRepository appointmentRepository;
    @Mock private AppointmentStatusRepository appointmentStatusRepository;
    @Mock private com.careercompass.repository.AcademicRecordRepository academicRecordRepository;
    @Mock private com.careercompass.service.TranscriptService transcriptService;
    @Mock private com.careercompass.integration.ai.DataAnalysisClient dataAnalysisClient;

    @InjectMocks
    private ConsultationService consultationService;

    // Purpose: List Available Mentors - throws When Career Path Not Set.
    @Test
    void listAvailableMentors_throwsWhenCareerPathNotSet() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(null).build();
        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));

        assertThatThrownBy(() -> consultationService.listAvailableMentors(1))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }

    // Purpose: List Available Mentors - returns AI Ranked Mentors.
    @Test
    void listAvailableMentors_returnsAIRankedMentors() {
        CareerPath path = CareerPath.builder().title("Software Engineering").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(path).build();

        Expert mentor = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor")
                .studyField(StudyField.builder().fieldName("Computer Science").build())
                .fieldStartingYear((short) 2010).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findByStatus_StatusName("Active")).thenReturn(List.of(mentor));
        when(academicRecordRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of());
        when(transcriptService.latestQuizScoresBySkillId(1)).thenReturn(java.util.Map.of());
        
        com.careercompass.integration.dto.MentorMatchResponse aiResponse = com.careercompass.integration.dto.MentorMatchResponse.builder()
                .items(List.of(com.careercompass.integration.dto.MentorMatchResponse.MentorMatchItem.builder()
                        .mentorId("20")
                        .score(0.85)
                        .gapsAddressed(2)
                        .explanation("Match explanation")
                        .build()))
                .build();
                
        when(dataAnalysisClient.matchMentors(any(com.careercompass.integration.dto.MentorMatchRequest.class)))
                .thenReturn(aiResponse);

        List<MentorSummaryResponse> mentors = consultationService.listAvailableMentors(1);

        assertThat(mentors).hasSize(1);
        assertThat(mentors.get(0).getExpertId()).isEqualTo(20);
        assertThat(mentors.get(0).getMatchScore()).isEqualTo(0.85);
        assertThat(mentors.get(0).getGapsAddressed()).isEqualTo(2);
        assertThat(mentors.get(0).getMatchReason()).isEqualTo("Match explanation");
    }


    // Purpose: Book Session - creates Appointment With Requested Status.
    @Test
    void bookSession_createsAppointmentWithRequestedStatus() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).firstName("A").lastName("B").build();
        Expert expert = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor").build();
        AppointmentStatus requested = AppointmentStatus.builder().statusId(1).statusName("Requested").build();

        BookAppointmentRequest request = new BookAppointmentRequest();
        request.setExpertId(20);
        request.setAppointmentDate(LocalDateTime.now().plusDays(3));

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findById(20)).thenReturn(Optional.of(expert));
        when(appointmentStatusRepository.findByStatusName("Requested")).thenReturn(Optional.of(requested));
        when(appointmentRepository.save(any(Appointment.class))).thenAnswer(inv -> {
            Appointment a = inv.getArgument(0);
            a.setAppointmentId(100);
            return a;
        });

        AppointmentResponse response = consultationService.bookSession(1, request);

        assertThat(response.getAppointmentId()).isEqualTo(100);
        assertThat(response.getStatusName()).isEqualTo("Requested");
        assertThat(response.getExpertId()).isEqualTo(20);
        assertThat(response.getJobseekerId()).isEqualTo(1);
    }
}
