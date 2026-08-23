package com.careercompass.exception;

import lombok.Getter;
import org.springframework.http.HttpStatus;

/**
 * A failure at the AI-service boundary, already translated into something the backend can answer
 * with.
 *
 * <p>Without this, a WebClient error surfaced as whatever it happened to be — a
 * {@code WebClientResponseException}, a timeout, or a {@link NullPointerException} thrown later
 * when code assumed a response list was non-null. All three reached the student as a generic
 * 500, and none of them said which dependency had failed.
 *
 * <p>{@code status} is the status the <em>backend</em> should answer with, not the one the AI
 * service returned. A 422 from the AI service means this backend sent a bad request, which is a
 * 502 to the student — their input was fine.
 */
@Getter
public class AiServiceException extends RuntimeException {

    private final HttpStatus status;
    private final String errorCode;

    public AiServiceException(HttpStatus status, String errorCode, String message) {
        super(message);
        this.status = status;
        this.errorCode = errorCode;
    }

    public AiServiceException(HttpStatus status, String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.status = status;
        this.errorCode = errorCode;
    }
}
