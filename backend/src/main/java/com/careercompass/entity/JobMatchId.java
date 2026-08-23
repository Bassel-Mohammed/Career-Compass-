package com.careercompass.entity;

import jakarta.persistence.Embeddable;
import lombok.*;

import java.io.Serializable;

/**
 * Composite primary key for `job_matches` (job_id, jobseeker_id).
 */
@Embeddable
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@EqualsAndHashCode
public class JobMatchId implements Serializable {

    private Integer jobId;
    private Integer jobseekerId;
}
