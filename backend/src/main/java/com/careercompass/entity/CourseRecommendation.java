package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Maps to the `courses_recommendations` table.
 * Courses recommended to a job seeker by the AI pipeline (FR-JS-15/16).
 */
@Entity
@Table(name = "courses_recommendations")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CourseRecommendation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "recommendation_id")
    private Integer recommendationId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "jobseeker_id", nullable = false)
    private JobSeeker jobSeeker;

    @Column(name = "course_name", nullable = false, length = 200)
    private String courseName;

    @Column(name = "source_link", length = 500)
    private String sourceLink;

    /**
     * The skill this course was chosen to close, and why. Both come from the AI service with
     * every generated recommendation and are stored so a student revisiting the page keeps the
     * reasoning instead of being told to regenerate for it.
     *
     * <p>Nullable: rows created before these columns existed have no reasoning to show.
     */
    @Column(name = "targeted_skill_name", length = 200)
    private String targetedSkillName;

    @Column(name = "explanation", length = 1000)
    private String explanation;

    @Column(name = "recommended_at")
    private LocalDateTime recommendedAt;

    @PrePersist
    protected void onCreate() {
        if (recommendedAt == null) {
            recommendedAt = LocalDateTime.now();
        }
    }
}
