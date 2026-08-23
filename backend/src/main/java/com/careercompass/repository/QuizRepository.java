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
     * Every completed quiz for this job seeker, most recent first, used by TranscriptService to
     * apply the FR-JS-20 write-back (quiz results refine the grade-based skill score).
     *
     * <p>Fetched in one query and grouped by {@code skillId} in memory rather than queried once
     * per skill: a vector routinely holds 70+ skills, and a query each would be 70 round trips
     * on every dashboard load.
     */
    List<Quiz> findByJobSeeker_JobseekerIdAndTakenAtIsNotNullOrderByTakenAtDesc(Integer jobseekerId);

    void deleteByJobSeeker_JobseekerId(Integer jobseekerId);
}
