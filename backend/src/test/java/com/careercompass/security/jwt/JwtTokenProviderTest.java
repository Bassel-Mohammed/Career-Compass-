package com.careercompass.security.jwt;

import com.careercompass.security.Role;
import com.careercompass.security.userdetails.UserPrincipal;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class JwtTokenProviderTest {

    private JwtTokenProvider tokenProvider;

    @BeforeEach
    void setUp() {
        JwtProperties properties = new JwtProperties();
        // 32+ char secret required by HS256 signing (jjwt enforces a minimum key length).
        properties.setSecret("test-secret-key-for-unit-tests-only-1234567890");
        properties.setExpirationMinutes(30);
        tokenProvider = new JwtTokenProvider(properties);
    }

    // Purpose: Generates And Validates Token Round Trip.
    @Test
    void generatesAndValidatesTokenRoundTrip() {
        String token = tokenProvider.generateToken(42, "basil@example.com", Role.JOB_SEEKER);

        assertThat(token).isNotBlank();
        assertThat(tokenProvider.validateToken(token)).isTrue();

        UserPrincipal principal = tokenProvider.getPrincipalFromToken(token);
        assertThat(principal.getUserId()).isEqualTo(42);
        assertThat(principal.getEmail()).isEqualTo("basil@example.com");
        assertThat(principal.getRole()).isEqualTo(Role.JOB_SEEKER);
    }

    // Purpose: every issued token carries its own unique id (jti). This is what lets a single
    // session be revoked at logout without affecting the user's other sessions
    // (FR-JS-03, FR-CM-02, FR-EMP-03).
    @Test
    void everyIssuedTokenCarriesAUniqueId() {
        String first = tokenProvider.generateToken(42, "basil@example.com", Role.JOB_SEEKER);
        String second = tokenProvider.generateToken(42, "basil@example.com", Role.JOB_SEEKER);

        assertThat(tokenProvider.getTokenId(first)).isNotBlank();
        assertThat(tokenProvider.getTokenId(second)).isNotBlank();
        // Same user, same role, issued moments apart - the ids must still differ, otherwise
        // logging out of one session would silently revoke the other.
        assertThat(tokenProvider.getTokenId(first)).isNotEqualTo(tokenProvider.getTokenId(second));
    }

    // Purpose: the expiry can be read back off the token, so a denylist entry can be kept for
    // exactly as long as the token would otherwise have remained usable.
    @Test
    void exposesTheTokenExpiryForDenylistHousekeeping() {
        String token = tokenProvider.generateToken(42, "basil@example.com", Role.JOB_SEEKER);

        assertThat(tokenProvider.getExpiry(token))
                .isAfter(java.time.Instant.now())
                .isBefore(java.time.Instant.now().plusSeconds(31 * 60));
    }

    // Purpose: Rejects Tampered Token.
    @Test
    void rejectsTamperedToken() {
        String token = tokenProvider.generateToken(1, "a@example.com", Role.EMPLOYER);
        String tampered = token.substring(0, token.length() - 2) + "xx";

        assertThat(tokenProvider.validateToken(tampered)).isFalse();
    }

    // Purpose: Rejects Garbage Token.
    @Test
    void rejectsGarbageToken() {
        assertThat(tokenProvider.validateToken("not-a-real-jwt")).isFalse();
    }
}
