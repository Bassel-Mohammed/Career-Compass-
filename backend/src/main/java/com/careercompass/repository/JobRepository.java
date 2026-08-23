package com.careercompass.repository;

import com.careercompass.entity.Job;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `jobs`.
 * Supports FR-EMP-07/09/10 (post/edit/delete) and FR-JS-23 (match candidates browse jobs).
 */
public interface JobRepository extends JpaRepository<Job, Integer> {

    List<Job> findByEmployer_EmployerId(Integer employerId);

    Page<Job> findByIsActiveTrue(Pageable pageable);

    List<Job> findByStudyField_StudyFieldIdAndIsActiveTrue(Integer studyFieldId);
}
