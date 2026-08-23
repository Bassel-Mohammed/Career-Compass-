package com.careercompass.repository;

import com.careercompass.entity.QuizResponse;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `quiz_responses`.
 * Supports FR-JS-18/19 (attempt & evaluate quizzes).
 */
public interface QuizResponseRepository extends JpaRepository<QuizResponse, Integer> {

    List<QuizResponse> findByQuestion_Quiz_QuizId(Integer quizId);

    Optional<QuizResponse> findByQuestion_QuestionId(Integer questionId);

    /** Same erasure-fan-out reasoning as QuizQuestionRepository's deleteByQuiz_JobSeeker_... */
    void deleteByQuestion_Quiz_JobSeeker_JobseekerId(Integer jobseekerId);
}
