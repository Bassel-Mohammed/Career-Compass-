package com.careercompass.repository;

import com.careercompass.entity.QuizQuestion;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `quiz_questions`.
 */
public interface QuizQuestionRepository extends JpaRepository<QuizQuestion, Integer> {

    List<QuizQuestion> findByQuiz_QuizId(Integer quizId);

    /**
     * Used by JobSeekerService's erasure fan-out (NFR-PRIV-02). Bulk JPQL delete queries do
     * NOT trigger entity-level CascadeType.ALL (that only applies when removing managed
     * entities through the persistence context) — so quiz_questions must be deleted
     * explicitly before their parent quizzes, or the delete would fail on the FK constraint.
     * See QuizService's Javadoc / Increment 12's doc for where this was caught.
     */
    void deleteByQuiz_JobSeeker_JobseekerId(Integer jobseekerId);
}
