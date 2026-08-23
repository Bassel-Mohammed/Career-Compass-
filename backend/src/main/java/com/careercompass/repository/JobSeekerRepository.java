package com.careercompass.repository;

import com.careercompass.entity.JobSeeker;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `job_seekers`.
 * findByEmail supports FR-JS-01 (register — uniqueness check) / FR-JS-02 (login) / FR-JS-26.
 */
public interface JobSeekerRepository extends JpaRepository<JobSeeker, Integer> {

    Optional<JobSeeker> findByEmail(String email);

    boolean existsByEmail(String email);
}
