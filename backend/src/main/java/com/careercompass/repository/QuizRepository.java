package com.careercompass.repository;

import com.careercompass.entity.Quiz;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `quizzes`.
 * Supports FR-JS-17/18/19/20 (generate, attempt, evaluate quizzes; update skill profile).
 */
public interface QuizRepository extends JpaRepository<Quiz, Integer> {

    List<Quiz> findByJobSeeker_JobseekerIdOrderByGeneratedAtDesc(Integer jobseekerId);

    List<Quiz> findByJobSeeker_JobseekerIdAndTakenAtIsNull(Integer jobseekerId);

    /**
     * Latest completed quiz for a given course name, used by TranscriptService to apply the
     * FR-JS-20 write-back (quiz results refine the grade-based skill score) when recomputing
     * the skill dashboard. See TranscriptService's Javadoc for why courseName doubles as the
     * skill-matching key (a documented simplification, not an accident).
     */
    List<Quiz> findByJobSeeker_JobseekerIdAndCourseNameIgnoreCaseAndTakenAtIsNotNullOrderByTakenAtDesc(
            Integer jobseekerId, String courseName);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
