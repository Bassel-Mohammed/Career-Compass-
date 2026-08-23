package com.careercompass.service;

import com.careercompass.dto.request.JobPostRequest;
import com.careercompass.dto.response.JobResponse;
import com.careercompass.entity.Employer;
import com.careercompass.entity.Job;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.mapper.JobMapper;
import com.careercompass.repository.EmployerRepository;
import com.careercompass.repository.JobRepository;
import com.careercompass.repository.StudyFieldRepository;
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
 * Unit tests for JobService, with a particular focus on the ownership-check logic
 * (getOwnedJobOrThrow) — this is the part of the service that a path-prefix security rule
 * alone (ROLE_EMPLOYER) cannot cover, so it's the most important thing to verify here.
 */
@ExtendWith(MockitoExtension.class)
class JobServiceTest {

    @Mock private JobRepository jobRepository;
    @Mock private EmployerRepository employerRepository;
    @Mock private StudyFieldRepository studyFieldRepository;
    @Mock private JobMapper jobMapper;

    @InjectMocks
    private JobService jobService;

    // Purpose: Post Job - saves Job Linked To Calling Employer.
    @Test
    void postJob_savesJobLinkedToCallingEmployer() {
        Employer employer = Employer.builder().employerId(1).companyName("Acme").build();
        JobPostRequest request = new JobPostRequest();
        request.setTitle("Backend Engineer");
        request.setDescription("Build APIs.");

        when(employerRepository.findById(1)).thenReturn(Optional.of(employer));
        when(jobRepository.save(any(Job.class))).thenAnswer(inv -> {
            Job job = inv.getArgument(0);
            job.setJobId(10);
            return job;
        });
        when(jobMapper.toResponse(any(Job.class)))
                .thenReturn(JobResponse.builder().jobId(10).title("Backend Engineer").build());

        JobResponse response = jobService.postJob(1, request);

        assertThat(response.getJobId()).isEqualTo(10);
        verify(jobRepository).save(argThat(job -> job.getEmployer() == employer && job.getIsActive()));
    }

    // Purpose: Update Job - succeeds When Caller Owns The Job.
    @Test
    void updateJob_succeedsWhenCallerOwnsTheJob() {
        Employer owner = Employer.builder().employerId(1).build();
        Job job = Job.builder().jobId(10).employer(owner).build();

        JobPostRequest request = new JobPostRequest();
        request.setTitle("Updated Title");
        request.setDescription("Updated description.");

        when(jobRepository.findById(10)).thenReturn(Optional.of(job));
        when(jobRepository.save(any(Job.class))).thenAnswer(inv -> inv.getArgument(0));
        when(jobMapper.toResponse(any(Job.class)))
                .thenReturn(JobResponse.builder().title("Updated Title").build());

        JobResponse response = jobService.updateJob(1, 10, request);

        assertThat(response.getTitle()).isEqualTo("Updated Title");
    }

    // Purpose: Update Job - throws Unauthorized When Caller Does Not Own The Job.
    @Test
    void updateJob_throwsUnauthorizedWhenCallerDoesNotOwnTheJob() {
        Employer owner = Employer.builder().employerId(1).build();
        Job job = Job.builder().jobId(10).employer(owner).build();

        JobPostRequest request = new JobPostRequest();
        request.setTitle("Hijacked Title");

        when(jobRepository.findById(10)).thenReturn(Optional.of(job));

        // Employer 2 tries to edit employer 1's job.
        assertThatThrownBy(() -> jobService.updateJob(2, 10, request))
                .isInstanceOf(UnauthorizedActionException.class);

        verify(jobRepository, never()).save(any());
    }

    // Purpose: Delete Job - throws Unauthorized When Caller Does Not Own The Job.
    @Test
    void deleteJob_throwsUnauthorizedWhenCallerDoesNotOwnTheJob() {
        Employer owner = Employer.builder().employerId(1).build();
        Job job = Job.builder().jobId(10).employer(owner).build();

        when(jobRepository.findById(10)).thenReturn(Optional.of(job));

        assertThatThrownBy(() -> jobService.deleteJob(2, 10))
                .isInstanceOf(UnauthorizedActionException.class);

        verify(jobRepository, never()).delete(any(Job.class));
    }

    // Purpose: Delete Job - throws Not Found When Job Does Not Exist.
    @Test
    void deleteJob_throwsNotFoundWhenJobDoesNotExist() {
        when(jobRepository.findById(999)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> jobService.deleteJob(1, 999))
                .isInstanceOf(ResourceNotFoundException.class);
    }
}
