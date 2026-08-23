package com.careercompass.security.jwt;

import com.careercompass.security.Role;
import com.careercompass.security.userdetails.UserPrincipal;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

/**
 * Issues and validates signed JWTs (NFR-SEC-03: secure, signed session tokens).
 *
 * Claims embedded: subject = user id, plus `email` and `role` custom claims. This is what
 * lets {@link com.careercompass.security.userdetails.UserPrincipal} be reconstructed purely
 * from a validated token, without a database round-trip on every request (see UserPrincipal's
 * Javadoc for the reasoning).
 */
@Component
@RequiredArgsConstructor
public class JwtTokenProvider {

    private final JwtProperties jwtProperties;

    private SecretKey signingKey() {
        return Keys.hmacShaKeyFor(jwtProperties.getSecret().getBytes(StandardCharsets.UTF_8));
    }

    public String generateToken(Integer userId, String email, Role role) {
        Instant now = Instant.now();
        Instant expiry = now.plusSeconds(jwtProperties.getExpirationMinutes() * 60);

        return Jwts.builder()
                // A unique id per issued token. This is what makes logout possible: the
                // denylist can name one specific token without storing the token itself,
                // and without invalidating the user's other sessions (FR-JS-03/CM-02/EMP-03).
                .id(UUID.randomUUID().toString())
                .subject(String.valueOf(userId))
                .claim("email", email)
                .claim("role", role.name())
                .issuedAt(Date.from(now))
                .expiration(Date.from(expiry))
                .signWith(signingKey())
                .compact();
    }

    /** The token's `jti` claim. Assumes the token has already passed {@link #validateToken}. */
    public String getTokenId(String token) {
        return parseClaims(token).getId();
    }

    /** The token's own expiry, used to decide how long a denylist entry must be kept. */
    public Instant getExpiry(String token) {
        return parseClaims(token).getExpiration().toInstant();
    }

    public long getExpirationSeconds() {
        return jwtProperties.getExpirationMinutes() * 60;
    }

    /**
     * Validates the token's signature and expiry. Returns false (rather than throwing) for
     * any malformed/expired/invalid token so callers (the filter) can respond with a clean
     * 401 instead of leaking a stack trace (NFR-USE-03).
     */
    public boolean validateToken(String token) {
        try {
            Jwts.parser().verifyWith(signingKey()).build().parseSignedClaims(token);
            return true;
        } catch (JwtException | IllegalArgumentException e) {
            return false;
        }
    }

    public UserPrincipal getPrincipalFromToken(String token) {
        Claims claims = parseClaims(token);

        Integer userId = Integer.valueOf(claims.getSubject());
        String email = claims.get("email", String.class);
        Role role = Role.valueOf(claims.get("role", String.class));

        return new UserPrincipal(userId, email, role);
    }

    private Claims parseClaims(String token) {
        return Jwts.parser()
                .verifyWith(signingKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }
}
