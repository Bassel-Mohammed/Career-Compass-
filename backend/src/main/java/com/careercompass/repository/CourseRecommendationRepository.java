package com.careercompass.repository;

import com.careercompass.entity.CourseRecommendation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `courses_recommendations`.
 * Supports FR-JS-15/16 (view recommended courses tailored to career path).
 */
public interface CourseRecommendationRepository extends JpaRepository<CourseRecommendation, Integer> {

    List<CourseRecommendation> findByJobSeeker_JobseekerIdOrderByRecommendedAtDesc(Integer jobseekerId);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
