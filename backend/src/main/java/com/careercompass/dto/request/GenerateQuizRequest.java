package com.careercompass.dto.request;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-JS-17 (generate a quiz for one of the job seeker's skills).
 *
 * <p>Keyed by the canonical skill id the skill dashboard returns, not by a course name. A course
 * teaches many skills and a skill is taught by many courses, so a course-keyed quiz cannot be
 * written back to one skill without guessing — which FR-JS-20/21 must not do.
 */
@Getter
@Setter
public class GenerateQuizRequest {

    @NotBlank(message = "Skill id is required")
    private String skillId;

    /**
     * Bounded at 10 to match the AI contract: inference is serialised there, so an unbounded
     * count would starve every other caller.
     */
    @Min(1)
    @Max(10)
    private int questionCount = 5;
}
