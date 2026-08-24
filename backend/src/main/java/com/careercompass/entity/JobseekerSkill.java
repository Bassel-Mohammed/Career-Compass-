package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.Check;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * Maps to the `jobseeker_skills` table.
 * This is the persisted, per-skill breakdown behind the job seeker's Student Skill Vector
 * (Section 5.3.1) — `score` is written by Module 2 (deterministic scoring) and refined by
 * Module 5 (quiz write-back), per the AI methodology.
 */
@Entity
@Table(name = "jobseeker_skills")
@Check(name = "chk_jobseeker_skill_score", constraints = "score IS NULL OR score BETWEEN 0 AND 100")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class JobseekerSkill {

    @EmbeddedId
    private JobseekerSkillId id;

    @ManyToOne(fetch = FetchType.LAZY)
    @MapsId("jobseekerId")
    @JoinColumn(name = "jobseeker_id")
    private JobSeeker jobSeeker;

    @ManyToOne(fetch = FetchType.LAZY)
    @MapsId("skillId")
    @JoinColumn(name = "skill_id")
    private Skill skill;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "level_id", nullable = false)
    private Level level;

    @Column(name = "score", precision = 5, scale = 2)
    private BigDecimal score;

    /** Java-issued identity of the current persisted projection refresh. */
    @Column(name = "vector_version", length = 120)
    private String vectorVersion;

    /** Taxonomy version reported by the AI service for this projection, when available. */
    @Column(name = "taxonomy_version", length = 120)
    private String taxonomyVersion;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    @PreUpdate
    protected void onSave() {
        updatedAt = LocalDateTime.now();
    }
}
