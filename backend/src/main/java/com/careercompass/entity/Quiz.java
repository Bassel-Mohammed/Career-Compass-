package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.Check;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Maps to the `quizzes` table.
 * A generated quiz for a job seeker on a given course (FR-JS-17/18/19).
 */
@Entity
@Table(name = "quizzes")
@Check(name = "chk_quiz_score", constraints = "score IS NULL OR score BETWEEN 0 AND 100")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Quiz {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "quiz_id")
    private Integer quizId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "jobseeker_id", nullable = false)
    private JobSeeker jobSeeker;

    /**
     * Display subject of the quiz — the skill's label. Retained under its original column name
     * so existing rows and the NOT NULL constraint stay valid; a Flyway migration should rename
     * it to {@code subject} once ADR-011 lands. Do not join on it: this is display text, and
     * matching a course name against a skill name is precisely the ambiguity {@link #skillId}
     * exists to remove.
     */
    @Column(name = "course_name", nullable = false, length = 200)
    private String courseName;

    /**
     * Canonical skill id from the AI service's taxonomy — the key FR-JS-20/21's write-back
     * joins on. Nullable because quizzes generated before this column existed have no id and
     * must stay readable; they simply cannot update a skill until they are re-taken.
     */
    @Column(name = "skill_id", length = 120)
    private String skillId;

    @Column(name = "generated_at")
    private LocalDateTime generatedAt;

    @Column(name = "score", precision = 5, scale = 2)
    private BigDecimal score;

    @Column(name = "taken_at")
    private LocalDateTime takenAt;

    @Builder.Default
    @OneToMany(mappedBy = "quiz", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<QuizQuestion> questions = new ArrayList<>();

    @PrePersist
    protected void onCreate() {
        if (generatedAt == null) {
            generatedAt = LocalDateTime.now();
        }
    }
}
