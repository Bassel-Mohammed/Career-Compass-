package com.careercompass.exception;

/**
 * Thrown on login when the email/password combination is invalid.
 * Deliberately generic (doesn't say "wrong password" vs "no such account") to avoid
 * leaking which emails are registered (NFR-SEC-05 spirit — don't aid enumeration attacks).
 */
public class InvalidCredentialsException extends RuntimeException {
    public InvalidCredentialsException() {
        super("Invalid email or password.");
    }
}
