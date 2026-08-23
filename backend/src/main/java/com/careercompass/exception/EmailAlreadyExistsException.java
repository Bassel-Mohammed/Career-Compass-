package com.careercompass.exception;

/**
 * Thrown during registration when the email is already taken (FR-JS-01, FR-EMP-01, etc.
 * all require a unique email).
 */
public class EmailAlreadyExistsException extends RuntimeException {
    public EmailAlreadyExistsException(String email) {
        super("An account with email '" + email + "' already exists.");
    }
}
