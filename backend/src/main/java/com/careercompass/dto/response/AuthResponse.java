package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Response returned after successful login/registration
 * (FR-JS-27, FR-CM-7, FR-EMP-15, FR-SA-12, FR-EX-14 — "receive an authentication response").
 * Carries the JWT so the frontend can attach it as `Authorization: Bearer &lt;token&gt;`
 * on subsequent requests.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AuthResponse {

    private String token;
    private String tokenType; // "Bearer"
    private String role;      // JOB_SEEKER, CONTENT_MANAGER, EMPLOYER, ADMIN, EXPERT
    private Integer userId;
    private String email;
    private long expiresInSeconds;
}
