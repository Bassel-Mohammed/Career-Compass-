package com.careercompass.config;

import com.careercompass.dto.response.ApiErrorResponse;
import com.careercompass.security.jwt.JwtAuthFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Spring Security configuration for the Security Layer (Section 5.1, Figure 5.1.3).
 *
 * - Stateless sessions: every request is authenticated via the JWT in the Authorization
 *   header (NFR-SEC-03), no server-side session state.
 * - BCrypt password hashing (NFR-SEC-01).
 * - Role-based access control per actor (NFR-SEC-04) — endpoint-level rules below; method-level
 *   {@code @PreAuthorize} can be layered on top in the Service/Controller increments as needed.
 * - CORS configured for the (not-yet-built) frontend origin.
 */
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthFilter jwtAuthFilter;

    @Bean
    public PasswordEncoder passwordEncoder() {
        // NFR-SEC-01: bcrypt password hashing.
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http,
                                           AuthenticationEntryPoint restAuthenticationEntryPoint,
                                           AccessDeniedHandler restAccessDeniedHandler) throws Exception {
        http
                .csrf(csrf -> csrf.disable()) // stateless JWT API, not cookie/session based
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Without this block Spring Security falls back to its default entry point,
                // which answers an unauthenticated request with 403 FORBIDDEN. For a token-based
                // API that is the wrong signal: "you are not authenticated" (401, re-authenticate)
                // and "you are authenticated but not allowed here" (403, do not bother retrying)
                // are different outcomes, and the frontend needs to tell them apart to know
                // whether to redirect to the login screen (NFR-SEC-03/04, NFR-USE-03).
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(restAuthenticationEntryPoint)
                        .accessDeniedHandler(restAccessDeniedHandler))
                .authorizeHttpRequests(auth -> auth
                        // Logout is the one /api/auth route that needs a token: you cannot
                        // end a session without proving which session it is. This must be
                        // declared BEFORE the permitAll below, because Spring Security applies
                        // the first matching rule (FR-JS-03, FR-CM-02, FR-EMP-03).
                        .requestMatchers("/api/auth/logout").authenticated()
                        // Public: registration/login for every actor
                        .requestMatchers("/api/auth/**").permitAll()
                        // Public: API docs
                        .requestMatchers("/swagger-ui/**", "/v3/api-docs/**", "/swagger-ui.html").permitAll()
                        // Dev-only: H2 console (never enabled in prod profile)
                        .requestMatchers("/h2-console/**").permitAll()
                        // Shared lookup lists (universities, study fields, career paths). Any
                        // signed-in actor may read them: a job seeker needs the study field and
                        // career path ids to satisfy FR-JS-07/09, and a content manager needs the
                        // study field ids for FR-CM-05, but neither can reach /api/admin/**.
                        // Declared BEFORE the role rules below because the first match wins —
                        // moving it after them would leave it unreachable. Read-only; creating
                        // and editing these rows stays on /api/admin/** (FR-SA-07..10).
                        .requestMatchers(HttpMethod.GET, "/api/reference/**").authenticated()
                        // Role-scoped areas — refined further at the controller/method level
                        // as those controllers are built in later increments.
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .requestMatchers("/api/content-managers/**").hasRole("CONTENT_MANAGER")
                        .requestMatchers("/api/employers/**").hasRole("EMPLOYER")
                        .requestMatchers("/api/experts/**").hasRole("EXPERT")
                        .requestMatchers("/api/job-seekers/**").hasRole("JOB_SEEKER")
                        .anyRequest().authenticated()
                )
                // Needed for the H2 console's use of frames — dev profile only in practice.
                .headers(headers -> headers.frameOptions(frame -> frame.sameOrigin()))
                .addFilterBefore(jwtAuthFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    /**
     * Answers an UNAUTHENTICATED request (no token, expired token, or a malformed one that
     * JwtAuthFilter refused to trust) with 401 and the same {@link ApiErrorResponse} body
     * every other error in the API uses, so the frontend has one error shape to parse
     * (NFR-USE-03) rather than a Spring-generated HTML page or an empty body.
     */
    @Bean
    public AuthenticationEntryPoint restAuthenticationEntryPoint(ObjectMapper objectMapper) {
        return (request, response, authException) -> writeError(objectMapper, request, response,
                HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED",
                "You must sign in to access this resource.");
    }

    /**
     * Answers an AUTHENTICATED request that is not allowed here — a valid token for the wrong
     * role (NFR-SEC-04) — with 403. Deliberately a different status and error code from the
     * entry point above: retrying with fresh credentials would fix a 401, but never a 403.
     */
    @Bean
    public AccessDeniedHandler restAccessDeniedHandler(ObjectMapper objectMapper) {
        return (request, response, accessDeniedException) -> writeError(objectMapper, request, response,
                HttpStatus.FORBIDDEN, "FORBIDDEN",
                "You do not have permission to perform this action.");
    }

    /**
     * Both handlers above run inside the filter chain, before any controller is reached, so
     * GlobalExceptionHandler (a {@code @RestControllerAdvice}) never sees these failures and
     * cannot format them — hence writing the response body directly here.
     */
    private void writeError(ObjectMapper objectMapper,
                            HttpServletRequest request,
                            HttpServletResponse response,
                            HttpStatus status,
                            String errorCode,
                            String message) throws IOException {

        ApiErrorResponse body = ApiErrorResponse.builder()
                .timestamp(LocalDateTime.now())
                .status(status.value())
                .error(errorCode)
                .message(message)
                .path(request.getRequestURI())
                .build();

        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getWriter(), body);
    }

    private CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        // TODO: replace with the real frontend origin(s) once the frontend is deployed.
        configuration.setAllowedOrigins(List.of("http://localhost:3000", "http://localhost:5173"));
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}
