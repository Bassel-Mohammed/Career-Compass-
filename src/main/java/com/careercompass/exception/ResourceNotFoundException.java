package com.careercompass.exception;

/**
 * Generic "entity not found" exception, used across services (e.g. profile lookup by id).
 */
public class ResourceNotFoundException extends RuntimeException {
    public ResourceNotFoundException(String message) {
        super(message);
    }
}
