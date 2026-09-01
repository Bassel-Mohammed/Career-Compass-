package com.careercompass.repository;

import com.careercompass.entity.JobMatch;
import com.careercompass.entity.JobMatchId;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `job_matches`.
 * Supports FR-JS-23 (job seeker's matches) and FR-EMP-11/12 (employer's matched candidates).
 */
public interface JobMatchRepository extends JpaRepository<JobMatch, JobMatchId> {

    List<JobMatch> findByJobSeeker_JobseekerIdOrderByMatchScoreDesc(Integer jobseekerId);

    List<JobMatch> findByJob_JobIdOrderByMatchScoreDesc(Integer jobId);

    /** Remove persisted candidate matches before deleting their posting. */
    void deleteByJob_JobId(Integer jobId);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
