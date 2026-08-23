package com.careercompass.service;

import com.careercompass.dto.request.JobPostRequest;
import com.careercompass.dto.response.JobResponse;
import com.careercompass.entity.Employer;
import com.careercompass.entity.Job;
import com.careercompass.entity.StudyField;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.mapper.JobMapper;
import com.careercompass.repository.EmployerRepository;
import com.careercompass.repository.JobRepository;
import com.careercompass.repository.StudyFieldRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Business Layer for job postings (FR-EMP-07/08/09/10).
 *
 * Every mutating method takes the caller's OWN employerId (resolved server-side from the JWT,
 * same pattern as JobSeekerService/CurrentUser from Increment 7) AND re-checks that the target
 * job actually belongs to that employer before allowing an edit/delete — this is the
 * "ownership check" layer that a simple ROLE_EMPLOYER path rule in SecurityConfig cannot
 * provide on its own (that only proves "some employer", not "the RIGHT employer").
 */
@Service
@RequiredArgsConstructor
public class JobService {

    private final JobRepository jobRepository;
    private final EmployerRepository employerRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final JobMapper jobMapper;

    @Transactional
    public JobResponse postJob(Integer employerId, JobPostRequest request) {
        Employer employer = employerRepository.findById(employerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Employer with id " + employerId + " not found."));

        StudyField studyField = resolveStudyField(request.getStudyFieldId());

        Job job = Job.builder()
                .employer(employer)
                .studyField(studyField)
                .title(request.getTitle())
                .description(request.getDescription())
                .requiredSkills(request.getRequiredSkills())
                .isActive(true)
                .build();

        return jobMapper.toResponse(jobRepository.save(job));
    }

    @Transactional
    public JobResponse updateJob(Integer employerId, Integer jobId, JobPostRequest request) {
        Job job = getOwnedJobOrThrow(employerId, jobId);

        job.setTitle(request.getTitle());
        job.setDescription(request.getDescription());
        job.setRequiredSkills(request.getRequiredSkills());
        job.setStudyField(resolveStudyField(request.getStudyFieldId()));

        return jobMapper.toResponse(jobRepository.save(job));
    }

    @Transactional
    public void deleteJob(Integer employerId, Integer jobId) {
        Job job = getOwnedJobOrThrow(employerId, jobId);
        jobRepository.delete(job);
    }

    @Transactional(readOnly = true)
    public List<JobResponse> listMyJobs(Integer employerId) {
        return jobRepository.findByEmployer_EmployerId(employerId).stream()
                .map(jobMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public Page<JobResponse> listActiveJobs(Pageable pageable) {
        return jobRepository.findByIsActiveTrue(pageable).map(jobMapper::toResponse);
    }

    private StudyField resolveStudyField(Integer studyFieldId) {
        if (studyFieldId == null) {
            return null;
        }
        return studyFieldRepository.findById(studyFieldId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Study field with id " + studyFieldId + " not found."));
    }

    private Job getOwnedJobOrThrow(Integer employerId, Integer jobId) {
        Job job = jobRepository.findById(jobId)
                .orElseThrow(() -> new ResourceNotFoundException("Job with id " + jobId + " not found."));

        if (!job.getEmployer().getEmployerId().equals(employerId)) {
            throw new UnauthorizedActionException(
                    "You do not have permission to modify this job posting.");
        }

        return job;
    }
}
