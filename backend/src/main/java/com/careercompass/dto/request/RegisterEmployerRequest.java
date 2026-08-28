package com.careercompass.dto.request;

import com.careercompass.validation.PasswordPolicy;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-EMP-01 (employer registration).
 */
@Getter
@Setter
public class RegisterEmployerRequest {

    @NotBlank(message = "Company name is required")
    @Size(max = 200)
    private String companyName;

    @Size(max = 150)
    private String industry;

    @NotBlank(message = "Email is required")
    @Email(message = "Email must be a valid address")
    @Size(max = 255)
    private String email;

    @NotBlank(message = "Password is required")
    @Size(min = 8, max = 100, message = "Password must be at least 8 characters")
    @Pattern(regexp = PasswordPolicy.PATTERN, message = PasswordPolicy.MESSAGE)
    private String password;

    @Size(max = 2000)
    private String companyDescription;
}
