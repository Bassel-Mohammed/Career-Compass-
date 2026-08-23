package com.careercompass.exception;

/**
 * Thrown when an action's precondition isn't satisfied yet — e.g. confirming a transcript
 * before a career path has been selected (FR-JS-09 must precede the skill-vector computation
 * that depends on it). A 400, since the request itself is well-formed but the account isn't
 * in the right state for it yet; distinct from validation errors on the request body itself.
 */
public class PrerequisiteNotMetException extends RuntimeException {
    public PrerequisiteNotMetException(String message) {
        super(message);
    }
}
