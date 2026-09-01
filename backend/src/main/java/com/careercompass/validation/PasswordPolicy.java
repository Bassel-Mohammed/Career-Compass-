package com.careercompass.validation;

/** Shared validation constants for every endpoint that accepts a new password. */
public final class PasswordPolicy {

    /** At least one letter and one non-whitespace, non-alphanumeric symbol. */
    public static final String PATTERN = "^(?=.*[A-Za-z])(?=.*[^A-Za-z0-9\\s]).+$";

    public static final String MESSAGE =
            "Password must include at least one letter and one symbol";

    private PasswordPolicy() {
    }
}
