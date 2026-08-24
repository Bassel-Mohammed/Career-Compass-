package com.careercompass.service;

import com.careercompass.dto.response.CandidateMatchResult;
import com.careercompass.dto.response.JobMatchResult;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.JobMatchRequest;
import com.careercompass.integration.dto.JobMatchResponse;
import com.careercompass.repository.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for JobMatchService (FR-JS-23, FR-EMP-11/12). Focused on: the precondition check
 * (no skill profile yet), the ownership check on the employer side (same pattern as
 * JobService, Increment 8), correct sorting by descending match score, and that matches get
 * persisted via JobMatchRepository (not just returned transiently).
 */
@ExtendWith(MockitoExtension.class)
class JobMatchServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private JobRepository jobRepository;
    @Mock private JobseekerSkillRepository jobseekerSkillRepository;
    @Mock private JobMatchRepository jobMatchRepository;
    @Mock private DataAnalysisClient dataAnalysisClient;

    @InjectMocks
    private JobMatchService jobMatchService;

    // Purpose: Match Job Seeker To Jobs - throws When No Skill Profile Exists.
    @Test
    void matchJobSeekerToJobs_throwsWhenNoSkillProfileExists() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(jobseekerSkillRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of());

        assertThatThrownBy(() -> jobMatchService.matchJobSeekerToJobs(1))
                .isInstanceOf(PrerequisiteNotMetException.class);

        verify(jobRepository, never()).findByIsActiveTrue(any());
    }

    // Purpose: Match Job Seeker To Jobs - returns Results Sorted By Descending Score.
    @Test
    void matchJobSeekerToJobs_returnsResultsSortedByDescendingScore() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        Skill skill = Skill.builder().skillId(1).skillName("Java").build();
        Level level = Level.builder().levelId(1).levelName("Advanced").build();
        JobseekerSkill jss = JobseekerSkill.builder()
                .id(new JobseekerSkillId(1, 1)).jobSeeker(jobSeeker).skill(skill).level(level)
                .score(BigDecimal.valueOf(80)).build();

        Employer employer = Employer.builder().employerId(10).companyName("Acme").build();
        Job lowMatchJob = Job.builder().jobId(100).title("Low Match").employer(employer).build();
        Job highMatchJob = Job.builder().jobId(101).title("High Match").employer(employer).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(jobseekerSkillRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of(jss));
        when(jobRepository.findByIsActiveTrue(any()))
                .thenReturn(new PageImpl<>(List.of(lowMatchJob, highMatchJob)));

        when(dataAnalysisClient.scoreJobMatch(argThat(
                        r -> r != null && "Low Match".equals(r.getJobTitle()))))
                .thenReturn(JobMatchResponse.builder().matchScore(BigDecimal.valueOf(40)).explanation("meh").build());
        when(dataAnalysisClient.scoreJobMatch(argThat(
                        r -> r != null && "High Match".equals(r.getJobTitle()))))
                .thenReturn(JobMatchResponse.builder().matchScore(BigDecimal.valueOf(90)).explanation("great fit").build());

        when(jobMatchRepository.findById(any())).thenReturn(Optional.empty());
        when(jobMatchRepository.save(any(JobMatch.class))).thenAnswer(inv -> inv.getArgument(0));

        List<JobMatchResult> results = jobMatchService.matchJobSeekerToJobs(1);

        assertThat(results).hasSize(2);
        assertThat(results.get(0).getJobTitle()).isEqualTo("High Match"); // sorted descending
        assertThat(results.get(0).getMatchScore()).isEqualByComparingTo(BigDecimal.valueOf(90));
        assertThat(results.get(1).getJobTitle()).isEqualTo("Low Match");

        verify(jobMatchRepository, times(2)).save(any(JobMatch.class));
    }

    // Purpose: Match Candidates For Job - throws Unauthorized When Employer Does Not Own The Job.
    @Test
    void matchCandidatesForJob_throwsUnauthorizedWhenEmployerDoesNotOwnTheJob() {
        Employer owner = Employer.builder().employerId(1).build();
        Job job = Job.builder().jobId(10).employer(owner).build();

        when(jobRepository.findById(10)).thenReturn(Optional.of(job));

        assertThatThrownBy(() -> jobMatchService.matchCandidatesForJob(2, 10))
                .isInstanceOf(UnauthorizedActionException.class);
    }

    // Purpose: Match Candidates For Job - only Includes Candidates With A Skill Profile.
    @Test
    void matchCandidatesForJob_onlyIncludesCandidatesWithASkillProfile() {
        Employer owner = Employer.builder().employerId(1).build();
        Job job = Job.builder().jobId(10).employer(owner).title("Backend Engineer").build();

        JobSeeker withSkills = JobSeeker.builder().jobseekerId(1).firstName("Has").lastName("Skills")
                .email("has@example.com").build();
        JobSeeker withoutSkills = JobSeeker.builder().jobseekerId(2).firstName("No").lastName("Skills")
                .email("no@example.com").build();

        Skill skill = Skill.builder().skillId(1).skillName("Java").build();
        Level level = Level.builder().levelId(1).levelName("Advanced").build();
        JobseekerSkill jss = JobseekerSkill.builder()
                .id(new JobseekerSkillId(1, 1)).jobSeeker(withSkills).skill(skill).level(level)
                .score(BigDecimal.valueOf(85)).build();

        when(jobRepository.findById(10)).thenReturn(Optional.of(job));
        when(jobSeekerRepository.findAll()).thenReturn(List.of(withSkills, withoutSkills));
        when(jobseekerSkillRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of(jss));
        when(jobseekerSkillRepository.findByJobSeeker_JobseekerId(2)).thenReturn(List.of());

        when(dataAnalysisClient.scoreJobMatch(any(JobMatchRequest.class)))
                .thenReturn(JobMatchResponse.builder().matchScore(BigDecimal.valueOf(75)).explanation("solid").build());
        when(jobMatchRepository.findById(any())).thenReturn(Optional.empty());
        when(jobMatchRepository.save(any(JobMatch.class))).thenAnswer(inv -> inv.getArgument(0));

        List<CandidateMatchResult> results = jobMatchService.matchCandidatesForJob(1, 10);

        assertThat(results).hasSize(1);
        assertThat(results.get(0).getJobseekerId()).isEqualTo(1);
        assertThat(results.get(0).getSkillInsights()).hasSize(1);
        assertThat(results.get(0).getEmail()).isEqualTo("has@example.com"); // FR-EMP-13 support
    }
}
