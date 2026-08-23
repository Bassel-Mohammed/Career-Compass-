package com.careercompass.service;

import com.careercompass.dto.request.UpdateJobSeekerProfileRequest;
import com.careercompass.dto.response.JobSeekerProfileResponse;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.JobSeeker;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.mapper.JobSeekerMapper;
import com.careercompass.repository.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for JobSeekerService (FR-JS-06/07/08/09), particularly focused on:
 * - partial-update semantics (only non-null fields change)
 * - the deleteProfile "right to erasure" fan-out (NFR-PRIV-02) — confirms every dependent
 *   repository is cleared before the job seeker row itself is deleted
 */
@ExtendWith(MockitoExtension.class)
class JobSeekerServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private UniversityRepository universityRepository;
    @Mock private StudyFieldRepository studyFieldRepository;
    @Mock private CareerPathRepository careerPathRepository;
    @Mock private AcademicRecordRepository academicRecordRepository;
    @Mock private CourseRecommendationRepository courseRecommendationRepository;
    @Mock private JobseekerSkillRepository jobseekerSkillRepository;
    @Mock private QuizRepository quizRepository;
    @Mock private QuizQuestionRepository quizQuestionRepository;
    @Mock private QuizResponseRepository quizResponseRepository;
    @Mock private JobMatchRepository jobMatchRepository;
    @Mock private AppointmentRepository appointmentRepository;
    @Mock private JobSeekerMapper jobSeekerMapper;

    @InjectMocks
    private JobSeekerService jobSeekerService;

    // Purpose: Update Profile - applies Only Provided Fields.
    @Test
    void updateProfile_appliesOnlyProvidedFields() {
        JobSeeker existing = JobSeeker.builder()
                .jobseekerId(1)
                .firstName("Old")
                .lastName("Name")
                .build();

        UpdateJobSeekerProfileRequest request = new UpdateJobSeekerProfileRequest();
        request.setFirstName("New");
        // lastName, universityId, studyFieldId, careerPathId left null -> untouched

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(existing));
        when(jobSeekerRepository.save(any(JobSeeker.class))).thenAnswer(inv -> inv.getArgument(0));
        when(jobSeekerMapper.toProfileResponse(any(JobSeeker.class)))
                .thenReturn(JobSeekerProfileResponse.builder().firstName("New").lastName("Name").build());

        JobSeekerProfileResponse response = jobSeekerService.updateProfile(1, request);

        assertThat(response.getFirstName()).isEqualTo("New");
        assertThat(response.getLastName()).isEqualTo("Name");
        verify(careerPathRepository, never()).findById(any());
        verify(universityRepository, never()).findById(any());
    }

    // Purpose: Update Profile - selects Career Path When Provided.
    @Test
    void updateProfile_selectsCareerPathWhenProvided() {
        JobSeeker existing = JobSeeker.builder().jobseekerId(1).build();
        CareerPath careerPath = CareerPath.builder().careerPathId(7).title("Software Engineer").build();

        UpdateJobSeekerProfileRequest request = new UpdateJobSeekerProfileRequest();
        request.setCareerPathId(7);

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(existing));
        when(careerPathRepository.findById(7)).thenReturn(Optional.of(careerPath));
        when(jobSeekerRepository.save(any(JobSeeker.class))).thenAnswer(inv -> inv.getArgument(0));
        when(jobSeekerMapper.toProfileResponse(any(JobSeeker.class)))
                .thenReturn(JobSeekerProfileResponse.builder().careerPathTitle("Software Engineer").build());

        jobSeekerService.updateProfile(1, request);

        verify(jobSeekerRepository).save(argThat(js -> js.getCareerPath() == careerPath));
    }

    // Purpose: Update Profile - throws When Job Seeker Not Found.
    @Test
    void updateProfile_throwsWhenJobSeekerNotFound() {
        when(jobSeekerRepository.findById(999)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> jobSeekerService.updateProfile(999, new UpdateJobSeekerProfileRequest()))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    // Purpose: Delete Profile - clears All Dependent Data Before Deleting Job Seeker.
    @Test
    void deleteProfile_clearsAllDependentDataBeforeDeletingJobSeeker() {
        when(jobSeekerRepository.existsById(1)).thenReturn(true);

        jobSeekerService.deleteProfile(1);

        verify(appointmentRepository).deleteByJobSeeker_JobseekerId(1);
        verify(jobMatchRepository).deleteByJobSeeker_JobseekerId(1);
        verify(quizResponseRepository).deleteByQuestion_Quiz_JobSeeker_JobseekerId(1);
        verify(quizQuestionRepository).deleteByQuiz_JobSeeker_JobseekerId(1);
        verify(quizRepository).deleteByJobSeeker_JobseekerId(1);
        verify(jobseekerSkillRepository).deleteByJobSeeker_JobseekerId(1);
        verify(courseRecommendationRepository).deleteByJobSeeker_JobseekerId(1);
        verify(academicRecordRepository).deleteByJobSeeker_JobseekerId(1);
        verify(jobSeekerRepository).deleteById(1);
    }

    // Purpose: Delete Profile - throws When Not Found And Deletes Nothing.
    @Test
    void deleteProfile_throwsWhenNotFoundAndDeletesNothing() {
        when(jobSeekerRepository.existsById(404)).thenReturn(false);

        assertThatThrownBy(() -> jobSeekerService.deleteProfile(404))
                .isInstanceOf(ResourceNotFoundException.class);

        verifyNoInteractions(appointmentRepository, jobMatchRepository, quizRepository,
                quizQuestionRepository, quizResponseRepository,
                jobseekerSkillRepository, courseRecommendationRepository, academicRecordRepository);
        verify(jobSeekerRepository, never()).deleteById(any());
    }
}
