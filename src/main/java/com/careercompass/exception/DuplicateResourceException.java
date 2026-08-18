package com.careercompass.exception;

/**
 * Generic "this would create a duplicate" exception for uniqueness violations that aren't
 * email-specific (e.g. a study field name, a career path title within a field). Kept separate
 * from {@link EmailAlreadyExistsException} since that one carries auth-specific semantics.
 */
public class DuplicateResourceException extends RuntimeException {
    public DuplicateResourceException(String message) {
        super(message);
    }
}
