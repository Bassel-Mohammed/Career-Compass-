package com.careercompass.repository;

import com.careercompass.entity.AcademicRecord;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `academic_records`.
 * Extracted transcript data (FR-JS-11); read for skill-vector computation (FR-JS-12/13/22).
 */
public interface AcademicRecordRepository extends JpaRepository<AcademicRecord, Integer> {

    List<AcademicRecord> findByJobSeeker_JobseekerId(Integer jobseekerId);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
