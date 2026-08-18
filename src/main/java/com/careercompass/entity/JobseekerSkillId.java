package com.careercompass.entity;

import jakarta.persistence.Embeddable;
import lombok.*;

import java.io.Serializable;

/**
 * Composite primary key for `jobseeker_skills` (jobseeker_id, skill_id).
 */
@Embeddable
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@EqualsAndHashCode
public class JobseekerSkillId implements Serializable {

    private Integer jobseekerId;
    private Integer skillId;
}
