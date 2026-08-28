package com.careercompass.security.jwt;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;

/**
 * Binds the `careercompass.jwt.*` block from application.yml.
 * `secret` MUST come from an environment variable in any non-dev environment (NFR-SEC-07).
 */
@Component
@ConfigurationProperties(prefix = "careercompass.jwt")
@Validated
@Getter
@Setter
public class JwtProperties {

    @NotBlank(message = "JWT secret is required and must be provided via the JWT_SECRET environment variable.")
    @Size(min = 32, message = "JWT secret must be at least 32 characters long to be cryptographically secure.")
    private String secret;

    /** Session length; also the inactivity-logout window (FR-JS-04, FR-CM-03, FR-EMP-04). */
    private long expirationMinutes = 30;
}
