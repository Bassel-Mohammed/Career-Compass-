package com.careercompass.exception;

/** Raised when a review mutation was based on an older draft/row version. */
public class StaleResourceException extends RuntimeException {
    public StaleResourceException(String message) {
        super(message);
    }
}
