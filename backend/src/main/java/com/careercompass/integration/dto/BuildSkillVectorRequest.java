package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * Request to Module 2 (Skill Vector, Section 5.3.3).
 *
 * <p>The AI service is stateless and holds no students, so the confirmed transcript rows travel
 * on every call. {@code courseCode} is the deterministic join key to the course-skill map and
 * must survive from extraction all the way here — a course name will not join reliably.
 *
 * <p>{@code quizScores} maps canonical skill id to a graded quiz result in {@code 0..100}
 * (Java's scale; the adapter converts to the contract's {@code 0.0..1.0}). Passing quiz evidence
 * here rather than patching the returned vector locally is what makes the AI service the single
 * component that computes a vector — Java grades and supplies evidence, Python does the maths.
 *
 * <p>{@code careerPathId} is retained for Java-side logging/traceability only. It is never sent:
 * a database-local integer means nothing to the other service.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BuildSkillVectorRequest {
    private Integer jobseekerId;
    private Integer careerPathId;
    private List<CourseGradeDto> courses;
    private Map<String, BigDecimal> quizScores;
}
