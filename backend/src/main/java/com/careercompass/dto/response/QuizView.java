package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * A quiz as shown to the job seeker (FR-JS-17/18). `score`/`takenAt` are null until the quiz
 * has been submitted.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizView {
    private Integer quizId;
    private String courseName;
    private LocalDateTime generatedAt;
    private BigDecimal score;
    private LocalDateTime takenAt;
    private List<QuizQuestionView> questions;
}
