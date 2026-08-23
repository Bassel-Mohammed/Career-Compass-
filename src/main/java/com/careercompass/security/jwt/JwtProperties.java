package com.careercompass.security.jwt;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Binds the `careercompass.jwt.*` block from application.yml.
 * `secret` MUST come from an environment variable in any non-dev environment (NFR-SEC-07).
 */
@Component
@ConfigurationProperties(prefix = "careercompass.jwt")
@Getter
@Setter
public class JwtProperties {

    private String secret;

    /** Session length; also the inactivity-logout window (FR-JS-04, FR-CM-03, FR-EMP-04). */
    private long expirationMinutes = 30;
}
