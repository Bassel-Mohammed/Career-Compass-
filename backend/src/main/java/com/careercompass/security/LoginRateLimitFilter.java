package com.careercompass.security;

import com.careercompass.dto.response.ApiErrorResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Throttles repeated failed sign-in attempts (NFR-SEC-01 supporting control).
 *
 * <p>All six login routes accepted unlimited attempts. Passwords are BCrypt-hashed, so a stolen
 * database is not trivially reversible, but nothing stopped an attacker simply asking the API
 * over and over — online brute force against a weak password needs no offline work at all.
 *
 * <p>Counting is per client IP <em>and</em> per submitted account, so one noisy office NAT
 * cannot lock out everybody behind it, and an attacker rotating IPs still cannot hammer a
 * single account. Only failures count: a correct password clears the counter, so an ordinary
 * user who mistypes twice and then succeeds is never delayed.
 *
 * <p>Deliberately in-process. A student-scale deployment runs one instance, and an in-memory
 * counter that works today beats a Redis dependency that is not there yet — but note this is
 * per-instance, so it does not survive a restart and does not coordinate across replicas. Move
 * the counter to shared storage before running more than one node (NFR-SCAL-02).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LoginRateLimitFilter extends OncePerRequestFilter {

    private final ObjectMapper objectMapper;

    @Value("${careercompass.security.login.max-attempts:10}")
    private int maxAttempts;

    @Value("${careercompass.security.login.lockout-minutes:15}")
    private long lockoutMinutes;

    private final Map<String, Attempts> attemptsByKey = new ConcurrentHashMap<>();

    /** Failure count and the instant the window opened. */
    private static final class Attempts {
        private final AtomicInteger count = new AtomicInteger();
        private volatile Instant windowStart = Instant.now();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Only the credential-checking routes. Logout carries a token and is not guessable.
        return !("POST".equals(request.getMethod())
                && request.getRequestURI().startsWith("/api/auth/")
                && request.getRequestURI().endsWith("/login"));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String key = clientKey(request);
        Attempts attempts = attemptsByKey.computeIfAbsent(key, k -> new Attempts());

        if (isLockedOut(attempts)) {
            log.warn("Rate-limited sign-in attempt for {}", key);
            writeTooManyRequests(request, response);
            return;
        }

        chain.doFilter(request, response);

        // 401 is what AuthService answers for a bad email or password; anything else (including
        // a validation error) is not a credential guess and must not count towards a lockout.
        if (response.getStatus() == HttpStatus.UNAUTHORIZED.value()) {
            attempts.count.incrementAndGet();
        } else if (response.getStatus() < HttpStatus.BAD_REQUEST.value()) {
            attemptsByKey.remove(key);
        }
    }

    private boolean isLockedOut(Attempts attempts) {
        if (Duration.between(attempts.windowStart, Instant.now()).toMinutes() >= lockoutMinutes) {
            // Window elapsed — forgive everything and start counting again.
            attempts.count.set(0);
            attempts.windowStart = Instant.now();
            return false;
        }
        return attempts.count.get() >= maxAttempts;
    }

    /**
     * IP plus the login path. The path carries the actor type, so exhausting attempts against
     * the admin route does not also lock this IP out of the student route.
     *
     * <p>Reads {@code X-Forwarded-For} first because behind a reverse proxy every request
     * otherwise shares the proxy's address and one attacker would rate-limit all users.
     */
    private String clientKey(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        String ip = (forwarded != null && !forwarded.isBlank())
                ? forwarded.split(",")[0].trim()
                : request.getRemoteAddr();
        return ip + "|" + request.getRequestURI();
    }

    private void writeTooManyRequests(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        ApiErrorResponse body = ApiErrorResponse.builder()
                .timestamp(LocalDateTime.now())
                .status(HttpStatus.TOO_MANY_REQUESTS.value())
                .error("TOO_MANY_ATTEMPTS")
                .message("Too many failed sign-in attempts. Wait " + lockoutMinutes
                        + " minutes and try again.")
                .path(request.getRequestURI())
                .build();

        response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Retry-After", String.valueOf(Duration.ofMinutes(lockoutMinutes).toSeconds()));
        objectMapper.writeValue(response.getWriter(), body);
    }
}
