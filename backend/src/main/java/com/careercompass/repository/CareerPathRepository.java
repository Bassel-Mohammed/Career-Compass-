package com.careercompass.repository;

import com.careercompass.entity.CareerPath;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `career_paths`.
 * Managed by System Administrator (FR-SA-08/09/10); browsed by Job Seeker (FR-JS-09).
 */
public interface CareerPathRepository extends JpaRepository<CareerPath, Integer> {

    List<CareerPath> findByStudyFields_StudyFieldId(Integer studyFieldId);

    Optional<CareerPath> findByCareerPathCode(String careerPathCode);
}
