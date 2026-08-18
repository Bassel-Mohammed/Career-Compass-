package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * Response for FR-JS-19 (evaluate quiz responses and calculate a score). Reveals the correct
 * option per question now that the attempt is over — safe to show once submitted, unlike
 * QuizQuestionView (shown before/during the attempt).
 *
 * `updatedDashboard` is included so the frontend can refresh the skill dashboard in the same
 * round-trip after a quiz is submitted, directly reflecting FR-JS-20/21 (skill profile and
 * dashboard updated based on quiz performance) without a second API call.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizResultResponse {
    private Integer quizId;
    private BigDecimal score; // 0-100
    private int correctCount;
    private int totalQuestions;
    private List<QuestionResult> questionResults;
    private SkillDashboardResponse updatedDashboard;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class QuestionResult {
        private Integer questionId;
        private String selectedOption;
        private String correctOption;
        private boolean correct;
    }
}
