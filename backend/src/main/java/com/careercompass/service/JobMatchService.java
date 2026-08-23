package com.careercompass.service;

import com.careercompass.dto.response.CandidateMatchResult;
import com.careercompass.dto.response.JobMatchResult;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.JobMatchRequest;
import com.careercompass.integration.dto.JobMatchResponse;
import com.careercompass.integration.dto.SkillScoreDto;
import com.careercompass.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.List;

/**
 * Business Layer for FR-JS-23 (job seeker's job matches) and FR-EMP-11/12 (employer's matched
 * candidates) — Module 6 (Job Matching, Section 5.3.3), the last module in the AI pipeline.
 *
 * Both directions score against the SAME persisted {@code jobseeker_skills} data (written by
 * TranscriptService/QuizService — see their Javadocs on the single-writer pattern); this
 * service only reads that data and calls {@link DataAnalysisClient#scoreJobMatch}, it never
 * computes or persists skill scores itself.
 *
 * <p><b>Performance note:</b> both methods call the AI service once PER (job seeker, job)
 * pair being scored — for {@link #matchJobSeekerToJobs}, once per active job; for
 * {@link #matchCandidatesForJob}, once per candidate with a skill profile. This is a simple,
 * correct implementation appropriate for a student-project data scale, but does not meet
 * NFR-PERF-05's 5-second target at any significant scale (dozens of jobs/candidates would
 * mean dozens of sequential AI calls). Flagged here and in the increment doc as a known
 * scalability limitation — batching multiple jobs/candidates into a single AI-service request,
 * or caching/precomputing matches asynchronously, would be the natural fix once real usage
 * volumes are known.
 */
@Service
@RequiredArgsConstructor
public class JobMatchService {

    private static final int MAX_CANDIDATES_PER_JOB = 20;

    private final JobSeekerRepository jobSeekerRepository;
    private final JobRepository jobRepository;
    private final JobseekerSkillRepository jobseekerSkillRepository;
    private final JobMatchRepository jobMatchRepository;
    private final DataAnalysisClient dataAnalysisClient;

    /** FR-JS-23: match the calling job seeker against currently active job postings. */
    @Transactional
    public List<JobMatchResult> matchJobSeekerToJobs(Integer jobseekerId) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Job seeker with id " + jobseekerId + " not found."));

        List<SkillScoreDto> skillVector = loadSkillVectorOrThrow(jobseekerId);

        List<Job> activeJobs = jobRepository.findByIsActiveTrue(Pageable.unpaged()).getContent();

        List<JobMatchResult> results = activeJobs.stream()
                .map(job -> {
                    JobMatchResponse scored = dataAnalysisClient.scoreJobMatch(JobMatchRequest.builder()
                            .skillVector(skillVector)
                            .jobTitle(job.getTitle())
                            .jobDescription(job.getDescription())
                            .jobRequiredSkills(job.getRequiredSkills())
                            .build());

                    JobMatch persisted = persistJobMatch(job, jobSeeker, scored);

                    return JobMatchResult.builder()
                            .jobId(job.getJobId())
                            .jobTitle(job.getTitle())
                            .companyName(job.getEmployer().getCompanyName())
                            .matchScore(persisted.getMatchScore())
                            .explanation(scored.getExplanation())
                            .matchedAt(persisted.getMatchedAt())
                            .build();
                })
                .sorted(Comparator.comparing(JobMatchResult::getMatchScore).reversed())
                .toList();

        return results;
    }

    /** FR-EMP-11/12: matched candidates for a specific job, with an ownership check. */
    @Transactional
    public List<CandidateMatchResult> matchCandidatesForJob(Integer employerId, Integer jobId) {
        Job job = jobRepository.findById(jobId)
                .orElseThrow(() -> new ResourceNotFoundException("Job with id " + jobId + " not found."));

        if (!job.getEmployer().getEmployerId().equals(employerId)) {
            throw new UnauthorizedActionException(
                    "You do not have permission to view candidates for this job.");
        }

        List<JobSeeker> candidates = jobSeekerRepository.findAll().stream()
                .filter(js -> !jobseekerSkillRepository.findByJobSeeker_JobseekerId(js.getJobseekerId()).isEmpty())
                .toList();

        List<CandidateMatchResult> results = candidates.stream()
                .map(candidate -> scoreCandidate(job, candidate))
                .sorted(Comparator.comparing(CandidateMatchResult::getMatchScore).reversed())
                .limit(MAX_CANDIDATES_PER_JOB)
                .toList();

        return results;
    }

    private CandidateMatchResult scoreCandidate(Job job, JobSeeker candidate) {
        List<JobseekerSkill> jobseekerSkills =
                jobseekerSkillRepository.findByJobSeeker_JobseekerId(candidate.getJobseekerId());

        List<SkillScoreDto> skillVector = jobseekerSkills.stream()
                .map(js -> SkillScoreDto.builder()
                        .skillName(js.getSkill().getSkillName())
                        .score(js.getScore())
                        .build())
                .toList();

        JobMatchResponse scored = dataAnalysisClient.scoreJobMatch(JobMatchRequest.builder()
                .skillVector(skillVector)
                .jobTitle(job.getTitle())
                .jobDescription(job.getDescription())
                .jobRequiredSkills(job.getRequiredSkills())
                .build());

        JobMatch persisted = persistJobMatch(job, candidate, scored);

        List<CandidateMatchResult.SkillInsight> insights = jobseekerSkills.stream()
                .map(js -> CandidateMatchResult.SkillInsight.builder()
                        .skillName(js.getSkill().getSkillName())
                        .score(js.getScore())
                        .build())
                .toList();

        return CandidateMatchResult.builder()
                .jobseekerId(candidate.getJobseekerId())
                .firstName(candidate.getFirstName())
                .lastName(candidate.getLastName())
                .email(candidate.getEmail())
                .matchScore(persisted.getMatchScore())
                .explanation(scored.getExplanation())
                .skillInsights(insights)
                .matchedAt(persisted.getMatchedAt())
                .build();
    }

    private List<SkillScoreDto> loadSkillVectorOrThrow(Integer jobseekerId) {
        List<JobseekerSkill> skills = jobseekerSkillRepository.findByJobSeeker_JobseekerId(jobseekerId);
        if (skills.isEmpty()) {
            throw new PrerequisiteNotMetException(
                    "Confirm your transcript (FR-JS-10/11) before viewing job matches.");
        }
        return skills.stream()
                .map(js -> SkillScoreDto.builder()
                        .skillName(js.getSkill().getSkillName())
                        .score(js.getScore())
                        .build())
                .toList();
    }

    private JobMatch persistJobMatch(Job job, JobSeeker jobSeeker, JobMatchResponse scored) {
        JobMatchId id = new JobMatchId(job.getJobId(), jobSeeker.getJobseekerId());
        JobMatch jobMatch = jobMatchRepository.findById(id)
                .orElse(JobMatch.builder().id(id).job(job).jobSeeker(jobSeeker).build());
        jobMatch.setMatchScore(scored.getMatchScore());
        return jobMatchRepository.save(jobMatch);
    }
}
