package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Request to Module 5 (Quiz and Evaluation, Section 5.3.3). `questionCount` lets the caller
 * bound the request; the report doesn't specify a fixed number of questions per quiz.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizGenerationRequest {
    private String courseName;
    private int questionCount;
}
