package com.careercompass.repository;

import com.careercompass.entity.RevokedToken;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;

/**
 * Data Access Layer for `revoked_tokens`.
 * Supports logout / session termination (FR-JS-03, FR-CM-02, FR-EMP-03).
 */
public interface RevokedTokenRepository extends JpaRepository<RevokedToken, String> {

    /**
     * Removes denylist rows for tokens that have expired on their own, so the table stays
     * proportional to the number of recent logouts rather than growing without limit.
     */
    void deleteByExpiresAtBefore(LocalDateTime cutoff);
}
