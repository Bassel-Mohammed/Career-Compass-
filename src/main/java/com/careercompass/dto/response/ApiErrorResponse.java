package com.careercompass.dto.response;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Standard error response shape used by the (not-yet-built) GlobalExceptionHandler.
 * Supports NFR-USE-03 (clear, non-technical error messages that state how to recover)
 * by giving the frontend one consistent, predictable JSON error shape to parse and display,
 * rather than raw stack traces or ad-hoc error formats per endpoint.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ApiErrorResponse {

    private LocalDateTime timestamp;
    private int status;
    private String error;      // short machine-friendly code, e.g. "VALIDATION_ERROR"
    private String message;    // human-readable, non-technical message (NFR-USE-03)
    private String path;

    /** Field-level validation errors, when applicable (e.g. from @Valid failures). */
    private List<FieldError> fieldErrors;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class FieldError {
        private String field;
        private String message;
    }
}
