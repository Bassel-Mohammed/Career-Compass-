package com.careercompass.exception;

/**
 * Thrown when an authenticated actor tries to act on a resource they don't own
 * (e.g. an Employer editing another Employer's job posting). Distinct from a generic
 * "not authenticated at all" 401 — this is a 403: the caller IS who they say they are,
 * they just aren't allowed to touch this particular resource.
 */
public class UnauthorizedActionException extends RuntimeException {
    public UnauthorizedActionException(String message) {
        super(message);
    }
}
