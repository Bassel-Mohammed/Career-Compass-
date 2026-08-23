package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A quiz question as shown to the job seeker while attempting the quiz (FR-JS-18).
 * Deliberately excludes `correctOption` — the same entity-vs-DTO boundary principle from
 * Increment 4, applied here for an obvious reason: showing the answer defeats the quiz.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizQuestionView {
    private Integer questionId;
    private String questionText;
    private String optionA;
    private String optionB;
    private String optionC;
    private String optionD;
}
