package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;

/**
 * A single skill's score/level within a {@link SkillDashboardResponse}
 * (FR-JS-13: classify Strong/Weak; Figure 5.4.6/5.4.7 in the report).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SkillLevelResponse {

    /** Java's local {@code skills} table id. Meaningless to the AI service. */
    private Integer skillId;

    /**
     * The AI service's canonical skill id. This is what a quiz request must carry, so the
     * dashboard has to surface it — otherwise the UI has only a label, and resolving a label
     * back to a skill is the ambiguity this whole identifier exists to remove.
     */
    private String canonicalSkillId;

    private String skillName;

    /** 0-100 current score. */
    private BigDecimal score;

    /** "Strong" / "Moderate" / "Weak" — derived from score vs. career-path target. */
    private String classification;

    /**
     * Short, human-readable explanation of why this score was produced (NFR-AI-04).
     * Optional — may be null when the source data doesn't provide one.
     */
    private String explanation;

    /** 0-100 target this career path asks for, derived from {@code requiredLevel}. */
    private BigDecimal targetScore;

    /** "beginner" / "intermediate" / "advanced" — how deeply the market wants this skill. */
    private String requiredLevel;

    /**
     * How much of the market asks for this skill, 0-100: the share of the career path's job
     * postings that named it.
     *
     * <p>Not the same quantity as {@code score} and not comparable to it. This says how much
     * the skill matters; {@code score} says how good the student is at it.
     */
    private BigDecimal importancePercent;

    /**
     * {@code importancePercent} bucketed into "critical", "important" or "useful" — the three
     * levels the dashboard groups by. Banded by the AI service beside the job-posting data that
     * justifies the thresholds, never recomputed here.
     */
    private String demandBand;

    /**
     * Postings that asked for this skill. Shown with {@code SkillDashboardResponse.sampleSize}
     * as "asked for in 72 of 184 postings" — the evidence behind the percentage, and the reason
     * a student has to believe it.
     */
    private Integer postingCount;

    /** Taxonomy type: "knowledge", "skill", "tool" or "soft". */
    private String skillType;

    /**
     * Shortfall weighted by demand. The dashboard's default order: a small gap in something
     * every posting asks for matters more than a large gap in something almost nobody does.
     */
    private BigDecimal priority;

    /** "grades", "grades+quizzes", "quizzes" or "transfer". */
    private String evidenceSource;

    /** Confirmed transcript courses whose extracted syllabi support this skill. */
    private List<SkillCourseEvidenceResponse> sourceCourses;
}
