package com.careercompass.security.jwt;

import com.careercompass.security.userdetails.UserPrincipal;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.lang.NonNull;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * Reads the `Authorization: Bearer &lt;token&gt;` header, validates the JWT, and — if valid —
 * populates the Spring Security context with a {@link UserPrincipal}-backed Authentication,
 * so downstream controllers/services can use {@code @PreAuthorize} / {@code hasRole(...)} and
 * inject the current principal.
 *
 * Requests with no/invalid token simply pass through with an empty SecurityContext; whether
 * that's acceptable is then decided by SecurityConfig's per-endpoint authorization rules
 * (e.g. public endpoints vs. `authenticated()`).
 */
@Component
@RequiredArgsConstructor
public class JwtAuthFilter extends OncePerRequestFilter {

    private static final String AUTH_HEADER = "Authorization";
    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtTokenProvider jwtTokenProvider;

    @Override
    protected void doFilterInternal(@NonNull HttpServletRequest request,
                                     @NonNull HttpServletResponse response,
                                     @NonNull FilterChain filterChain) throws ServletException, IOException {

        String token = extractToken(request);

        if (token != null && jwtTokenProvider.validateToken(token)) {
            UserPrincipal principal = jwtTokenProvider.getPrincipalFromToken(token);

            var authorities = List.of(new SimpleGrantedAuthority("ROLE_" + principal.getRole().name()));

            var authentication = new UsernamePasswordAuthenticationToken(principal, null, authorities);
            SecurityContextHolder.getContext().setAuthentication(authentication);
        }

        filterChain.doFilter(request, response);
    }

    private String extractToken(HttpServletRequest request) {
        String header = request.getHeader(AUTH_HEADER);
        if (header != null && header.startsWith(BEARER_PREFIX)) {
            return header.substring(BEARER_PREFIX.length());
        }
        return null;
    }
}
