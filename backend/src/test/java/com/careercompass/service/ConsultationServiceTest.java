package com.careercompass.service;

import com.careercompass.dto.request.BookAppointmentRequest;
import com.careercompass.dto.response.AppointmentResponse;
import com.careercompass.dto.response.MentorSummaryResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.repository.AppointmentRepository;
import com.careercompass.repository.AppointmentStatusRepository;
import com.careercompass.repository.ExpertAvailabilityRepository;
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.JobSeekerRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.time.LocalTime;
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
    @Mock private ExpertAvailabilityRepository expertAvailabilityRepository;
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
                        .score(new java.math.BigDecimal("85.0"))
                        .gapsAddressed(2)
                        .explanation("Match explanation")
                        .build()))
                .build();
                
        when(dataAnalysisClient.matchMentors(any(com.careercompass.integration.dto.MentorMatchRequest.class)))
                .thenReturn(aiResponse);

        List<MentorSummaryResponse> mentors = consultationService.listAvailableMentors(1);

        assertThat(mentors).hasSize(1);
        assertThat(mentors.get(0).getExpertId()).isEqualTo(20);
        assertThat(mentors.get(0).getMatchScore()).isEqualTo(new java.math.BigDecimal("85.0"));
        assertThat(mentors.get(0).getGapsAddressed()).isEqualTo(2);
        assertThat(mentors.get(0).getMatchReason()).isEqualTo("Match explanation");
    }


    /**
     * A fixed Monday well in the future. The booking rules key off the day of week, so a
     * relative date like {@code now().plusDays(3)} would drift across weekdays and make these
     * tests pass or fail depending on the day they are run.
     */
    private static final LocalDateTime MONDAY_10AM = LocalDateTime.of(2027, 1, 4, 10, 0);

    private void givenMondayMorningAvailability(Expert expert) {
        when(expertAvailabilityRepository.findByExpert_ExpertIdAndDayOfWeek(expert.getExpertId(), (byte) 1))
                .thenReturn(List.of(ExpertAvailability.builder()
                        .expert(expert)
                        .dayOfWeek((byte) 1)
                        .startTime(LocalTime.of(9, 0))
                        .endTime(LocalTime.of(12, 0))
                        .build()));
    }

    private static BookAppointmentRequest bookingFor(LocalDateTime when) {
        BookAppointmentRequest request = new BookAppointmentRequest();
        request.setExpertId(20);
        request.setAppointmentDate(when);
        return request;
    }

    // Purpose: Book Session - creates Appointment With Requested Status.
    @Test
    void bookSession_createsAppointmentWithRequestedStatus() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).firstName("A").lastName("B").build();
        Expert expert = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor").build();
        AppointmentStatus requested = AppointmentStatus.builder().statusId(1).statusName("Requested").build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findById(20)).thenReturn(Optional.of(expert));
        givenMondayMorningAvailability(expert);
        when(appointmentRepository.isSlotTaken(20, MONDAY_10AM)).thenReturn(false);
        when(appointmentStatusRepository.findByStatusName("Requested")).thenReturn(Optional.of(requested));
        when(appointmentRepository.save(any(Appointment.class))).thenAnswer(inv -> {
            Appointment a = inv.getArgument(0);
            a.setAppointmentId(100);
            return a;
        });

        AppointmentResponse response = consultationService.bookSession(1, bookingFor(MONDAY_10AM));

        assertThat(response.getAppointmentId()).isEqualTo(100);
        assertThat(response.getStatusName()).isEqualTo("Requested");
        assertThat(response.getExpertId()).isEqualTo(20);
        assertThat(response.getJobseekerId()).isEqualTo(1);
    }

    // Purpose: a mentor who has published no schedule at all cannot be booked. An empty
    // availability table means "I have not said when I am free", not "any time suits me".
    @Test
    void bookSession_rejectsMentorWithNoPublishedAvailability() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        Expert expert = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor").build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findById(20)).thenReturn(Optional.of(expert));
        when(expertAvailabilityRepository.findByExpert_ExpertIdAndDayOfWeek(20, (byte) 1))
                .thenReturn(List.of());

        assertThatThrownBy(() -> consultationService.bookSession(1, bookingFor(MONDAY_10AM)))
                .isInstanceOf(PrerequisiteNotMetException.class)
                .hasMessageContaining("has not published any availability");
    }

    // Purpose: a time on a day the mentor does publish, but outside every slot, is refused —
    // and the message names the slots that would have worked.
    @Test
    void bookSession_rejectsTimeOutsidePublishedSlots() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        Expert expert = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor").build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findById(20)).thenReturn(Optional.of(expert));
        givenMondayMorningAvailability(expert);

        // 15:00 on a Monday whose only slot is 09:00–12:00.
        assertThatThrownBy(() -> consultationService.bookSession(1, bookingFor(MONDAY_10AM.withHour(15))))
                .isInstanceOf(PrerequisiteNotMetException.class)
                .hasMessageContaining("09:00–12:00");
    }

    // Purpose: the slot end is exclusive, so back-to-back slots cannot both claim the
    // boundary minute and 12:00 is not bookable against a 09:00–12:00 slot.
    @Test
    void bookSession_treatsSlotEndAsExclusive() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        Expert expert = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor").build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findById(20)).thenReturn(Optional.of(expert));
        givenMondayMorningAvailability(expert);

        assertThatThrownBy(() -> consultationService.bookSession(1, bookingFor(MONDAY_10AM.withHour(12))))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }

    // Purpose: one mentor cannot be double-booked into the same instant, whether by two
    // students or by the same student clicking twice.
    @Test
    void bookSession_rejectsAlreadyTakenSlot() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        Expert expert = Expert.builder().expertId(20).firstName("Dr").lastName("Okafor").build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(expertRepository.findById(20)).thenReturn(Optional.of(expert));
        givenMondayMorningAvailability(expert);
        when(appointmentRepository.isSlotTaken(20, MONDAY_10AM)).thenReturn(true);

        assertThatThrownBy(() -> consultationService.bookSession(1, bookingFor(MONDAY_10AM)))
                .isInstanceOf(DuplicateResourceException.class)
                .hasMessageContaining("already been requested");
    }
}
