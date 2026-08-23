package com.careercompass.service;

import com.careercompass.entity.RevokedToken;
import com.careercompass.repository.RevokedTokenRepository;
import com.careercompass.security.jwt.JwtTokenProvider;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneId;

/**
 * Makes logout possible for every actor (FR-JS-03, FR-CM-02, FR-EMP-03).
 *
 * <h3>Why this class has to exist</h3>
 * A JWT is verified from its own signature, so the server holds nothing it could delete to
 * end a session. Left as-is, "logout" would mean nothing more than the client forgetting its
 * token — and a token copied from that client beforehand would keep working for the rest of
 * its 30-minute lifetime. Since the requirements give every actor the ability to log out,
 * the system needs a way to refuse a token it has already issued, which is what this denylist
 * provides.
 *
 * <h3>Why per-token rather than per-user</h3>
 * Revocation is keyed on the token's `jti`, so logging out ends the session that was actually
 * surrendered and leaves the user's other sessions alone. Recording a "valid from" timestamp
 * per user would have been cheaper, but it would sign a user out of every device at once,
 * which is a different behaviour from the one the requirements describe.
 *
 * <h3>Cost</h3>
 * The trade-off is a denylist lookup on every authenticated request, which is the price of
 * revocable stateless tokens. It is a primary-key lookup against a table holding only the
 * last 30 minutes of logouts, so it stays small; at production scale it belongs in an
 * in-memory cache (Redis) rather than the main database.
 */
@Service
@RequiredArgsConstructor
public class TokenRevocationService {

    private final RevokedTokenRepository revokedTokenRepository;
    private final JwtTokenProvider jwtTokenProvider;

    /**
     * Revokes a single token. Safe to call more than once for the same token: the jti is the
     * primary key, so a repeat save overwrites the existing row rather than duplicating it.
     */
    @Transactional
    public void revoke(String token) {
        String tokenId = jwtTokenProvider.getTokenId(token);
        LocalDateTime expiresAt = LocalDateTime.ofInstant(
                jwtTokenProvider.getExpiry(token), ZoneId.systemDefault());

        revokedTokenRepository.save(RevokedToken.builder()
                .tokenId(tokenId)
                .expiresAt(expiresAt)
                .revokedAt(LocalDateTime.now())
                .build());

        // Cheap opportunistic cleanup. Logout is infrequent enough that doing this inline
        // costs nothing, and it avoids introducing a scheduler for a single housekeeping job.
        purgeExpired();
    }

    /**
     * True if this token has been surrendered by a logout and has not yet expired.
     * Tokens issued before the `jti` claim existed have no id; those are treated as not
     * revoked rather than rejected, so adding this feature cannot invalidate a live session.
     */
    @Transactional(readOnly = true)
    public boolean isRevoked(String tokenId) {
        return tokenId != null && revokedTokenRepository.existsById(tokenId);
    }

    /** Discards denylist rows for tokens that have since expired on their own. */
    @Transactional
    public void purgeExpired() {
        revokedTokenRepository.deleteByExpiresAtBefore(LocalDateTime.now());
    }
}
