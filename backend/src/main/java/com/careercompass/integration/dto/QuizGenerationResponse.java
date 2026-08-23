package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response from Module 5. Maps directly onto `quiz_questions` fields when persisted.
 * Per NFR-AI-07 ("exactly one correct option per question"), `correctOption` must be one of
 * A/B/C/D — validated by the Java-side service layer before persistence (Section 5.3.3:
 * "validated against a JSON schema and graded programmatically rather than by the model").
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizGenerationResponse {
    private List<GeneratedQuizQuestionDto> questions;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class GeneratedQuizQuestionDto {
        private String questionText;
        private String optionA;
        private String optionB;
        private String optionC;
        private String optionD;
        private String correctOption; // "A" / "B" / "C" / "D"
    }
}
