package com.careercompass.config;

import com.careercompass.security.jwt.JwtAuthFilter;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

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
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable()) // stateless JWT API, not cookie/session based
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // Public: registration/login for every actor
                        .requestMatchers("/api/auth/**").permitAll()
                        // Public: API docs
                        .requestMatchers("/swagger-ui/**", "/v3/api-docs/**", "/swagger-ui.html").permitAll()
                        // Dev-only: H2 console (never enabled in prod profile)
                        .requestMatchers("/h2-console/**").permitAll()
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
