package com.careercompass.dto.request;

import com.careercompass.validation.PasswordPolicy;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * FR-*-02 supporting control: let a signed-in account rotate its own password.
 *
 * <p>The current password is required even though the caller already holds a valid token. A
 * token can be replayed from a machine the owner walked away from, or lifted by XSS; requiring
 * the existing secret means stealing a session is not by itself enough to take the account.
 */
@Getter
@Setter
public class ChangePasswordRequest {

    @NotBlank(message = "Current password is required")
    private String currentPassword;

    @NotBlank(message = "New password is required")
    @Size(min = 8, max = 100, message = "Password must be between 8 and 100 characters")
    @Pattern(regexp = PasswordPolicy.PATTERN, message = PasswordPolicy.MESSAGE)
    private String newPassword;
}
