package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * Maps to the `revoked_tokens` table: the denylist that makes logout possible
 * (FR-JS-03, FR-CM-02, FR-EMP-03).
 *
 * A JWT is self-contained and stateless by design — the server can verify it without
 * storing anything, which is exactly why it cannot simply be "cancelled". Logging out
 * therefore needs one piece of server-side state after all: a record of which tokens have
 * been surrendered, checked on every authenticated request.
 *
 * Only the token's `jti` claim is stored, never the token itself. The jti is a random UUID
 * that identifies the token without carrying the signature, so a leak of this table cannot
 * be replayed as a credential.
 *
 * `expiresAt` is copied from the token so the row can be discarded once the token would have
 * expired anyway. Without it the table would grow forever, while in practice a revoked token
 * only needs to be remembered for the remainder of its 30-minute lifetime.
 */
@Entity
@Table(name = "revoked_tokens")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RevokedToken {

    /** The token's `jti` claim — a random UUID, unique per issued token. */
    @Id
    @Column(name = "token_id", length = 64, nullable = false, updatable = false)
    private String tokenId;

    /** When the token would have expired on its own; the row is purged after this. */
    @Column(name = "expires_at", nullable = false)
    private LocalDateTime expiresAt;

    @Column(name = "revoked_at", nullable = false)
    private LocalDateTime revokedAt;
}
