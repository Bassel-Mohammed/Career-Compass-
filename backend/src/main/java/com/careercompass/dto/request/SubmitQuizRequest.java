package com.careercompass.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * Request body for FR-JS-18/19 (attempt a quiz / submit answers for evaluation).
 */
@Getter
@Setter
public class SubmitQuizRequest {

    @NotEmpty(message = "At least one answer is required")
    @Valid
    private List<QuizAnswerItem> answers;

    @Getter
    @Setter
    public static class QuizAnswerItem {

        @NotNull(message = "questionId is required")
        private Integer questionId;

        @NotNull(message = "selectedOption is required")
        @Pattern(regexp = "[A-Da-d]", message = "selectedOption must be one of A, B, C, D")
        private String selectedOption;
    }
}
