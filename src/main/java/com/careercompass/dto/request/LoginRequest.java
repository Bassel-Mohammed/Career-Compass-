package com.careercompass.dto.request;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;

/**
 * Shared login request body — used by every actor's login endpoint
 * (FR-JS-02, FR-CM-01, FR-EMP-02, FR-SA-01, FR-EX-01).
 * The actor type is determined by which controller/endpoint receives this DTO,
 * not by a field on the DTO itself.
 */
@Getter
@Setter
public class LoginRequest {

    @NotBlank(message = "Email is required")
    @Email(message = "Email must be a valid address")
    private String email;

    @NotBlank(message = "Password is required")
    private String password;
}
