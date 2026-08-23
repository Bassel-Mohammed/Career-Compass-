package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * A single recommended course from Module 4. Retrieved from the curated catalog rather than
 * generated (NFR-AI-05: the system cannot invent a course that does not exist), then ranked and
 * explained.
 *
 * <p>{@code sourceLink} is never blank by contract — it is the one output a student clicks
 * rather than reads, so the adapter rejects a row without one instead of persisting a dead card.
 *
 * <p>{@code targetedSkillId} is the canonical identity of the gap this course addresses;
 * {@code targetedSkillName} is its label, for display.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RecommendedCourseDto {
    private String courseName;
    private String sourceLink;
    private String targetedSkillId;
    private String targetedSkillName;
    private String explanation;
    /** Catalog retrieval score in 0..100 (converted from the contract's 0.0..1.0). */
    private BigDecimal relevancePercent;
    private String platform;
}
