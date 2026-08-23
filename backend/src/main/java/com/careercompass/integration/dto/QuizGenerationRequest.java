package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Request to Module 5 (Quiz and Evaluation, Section 5.3.3).
 *
 * <p>Keyed by canonical {@code skillId}, never by course name. A course teaches many skills and
 * a skill is taught by many courses, so a quiz labelled with a course cannot be written back to
 * a single skill without guessing — which is exactly what FR-JS-20/21 must not do.
 *
 * <p>{@code questionCount} is bounded by the AI service to 10: inference is serialised there, so
 * an unbounded count would starve every other caller.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QuizGenerationRequest {
    private String skillId;
    private int questionCount;
}
