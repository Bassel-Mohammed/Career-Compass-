package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response from Module 5, already normalised into the A/B/C/D shape the Java quiz tables and UI
 * use.
 *
 * <p>The wire contract returns an options array plus a <em>zero-based</em> correct index.
 * {@link com.careercompass.integration.ai.HttpDataAnalysisClient} converts that to a letter once,
 * at the boundary. That conversion is the single place an off-by-one could mis-grade every
 * attempt ever taken, so it is deliberately not spread across the service layer.
 *
 * <p>Per NFR-AI-07 there is exactly one correct option per question; {@code QuizService} still
 * validates that programmatically rather than trusting the response.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizGenerationResponse {
    private String skillId;
    private String skillLabel;
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
        private String explanation;
    }
}
