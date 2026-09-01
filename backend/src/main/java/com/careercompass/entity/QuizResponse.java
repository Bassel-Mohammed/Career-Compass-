package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Maps to the `quiz_responses` table.
 * A job seeker's answer to a single quiz question (FR-JS-19: evaluate quiz responses).
 */
@Entity
@Table(name = "quiz_responses",
        uniqueConstraints = @UniqueConstraint(name = "uq_quiz_response_question", columnNames = "question_id"))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class QuizResponse {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "response_id")
    private Integer responseId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "question_id", nullable = false)
    private QuizQuestion question;

    /** One of 'A', 'B', 'C', 'D' — DB-level CHECK constraint `chk_selected_option`. */
    @Column(name = "selected_option", nullable = false, length = 1)
    private String selectedOption;

    @Column(name = "is_correct", nullable = false)
    private Boolean isCorrect;

    @Column(name = "answered_at")
    private LocalDateTime answeredAt;

    @PrePersist
    protected void onCreate() {
        if (answeredAt == null) {
            answeredAt = LocalDateTime.now();
        }
    }
}
