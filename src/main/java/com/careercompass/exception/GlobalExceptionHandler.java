package com.careercompass.exception;

import com.careercompass.dto.response.ApiErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Translates exceptions into the consistent {@link ApiErrorResponse} shape (NFR-USE-03:
 * clear, non-technical error messages the frontend can render directly without special-casing
 * per endpoint).
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(EmailAlreadyExistsException.class)
    public ResponseEntity<ApiErrorResponse> handleEmailExists(EmailAlreadyExistsException ex,
                                                                HttpServletRequest request) {
        return build(HttpStatus.CONFLICT, "EMAIL_ALREADY_EXISTS", ex.getMessage(), request, null);
    }

    @ExceptionHandler({InvalidCredentialsException.class, BadCredentialsException.class})
    public ResponseEntity<ApiErrorResponse> handleInvalidCredentials(RuntimeException ex,
                                                                       HttpServletRequest request) {
        return build(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS",
                "Invalid email or password.", request, null);
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ApiErrorResponse> handleIllegalState(IllegalStateException ex,
                                                                  HttpServletRequest request) {
        // Used for upstream-AI-response problems (e.g. no well-formed quiz questions returned)
        // rather than a problem with the client's own request — 502, not 400.
        return build(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID", ex.getMessage(), request, null);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiErrorResponse> handleIllegalArgument(IllegalArgumentException ex,
                                                                     HttpServletRequest request) {
        return build(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", ex.getMessage(), request, null);
    }

    @ExceptionHandler(PrerequisiteNotMetException.class)
    public ResponseEntity<ApiErrorResponse> handlePrerequisiteNotMet(PrerequisiteNotMetException ex,
                                                                        HttpServletRequest request) {
        return build(HttpStatus.BAD_REQUEST, "PREREQUISITE_NOT_MET", ex.getMessage(), request, null);
    }

    @ExceptionHandler(UnauthorizedActionException.class)
    public ResponseEntity<ApiErrorResponse> handleUnauthorizedAction(UnauthorizedActionException ex,
                                                                        HttpServletRequest request) {
        return build(HttpStatus.FORBIDDEN, "FORBIDDEN", ex.getMessage(), request, null);
    }

    @ExceptionHandler(DuplicateResourceException.class)
    public ResponseEntity<ApiErrorResponse> handleDuplicateResource(DuplicateResourceException ex,
                                                                      HttpServletRequest request) {
        return build(HttpStatus.CONFLICT, "DUPLICATE_RESOURCE", ex.getMessage(), request, null);
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleNotFound(ResourceNotFoundException ex,
                                                              HttpServletRequest request) {
        return build(HttpStatus.NOT_FOUND, "NOT_FOUND", ex.getMessage(), request, null);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleValidation(MethodArgumentNotValidException ex,
                                                                HttpServletRequest request) {
        List<ApiErrorResponse.FieldError> fieldErrors = ex.getBindingResult().getFieldErrors().stream()
                .map(fe -> ApiErrorResponse.FieldError.builder()
                        .field(fe.getField())
                        .message(fe.getDefaultMessage())
                        .build())
                .toList();

        return build(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR",
                "One or more fields are invalid. Please check your input and try again.",
                request, fieldErrors);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> handleUnexpected(Exception ex, HttpServletRequest request) {
        // Deliberately generic message to the client (no stack trace / internal detail leaked);
        // real logging of `ex` happens via the logging framework, not shown here.
        return build(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "Something went wrong on our end. Please try again shortly.", request, null);
    }

    private ResponseEntity<ApiErrorResponse> build(HttpStatus status, String errorCode, String message,
                                                     HttpServletRequest request,
                                                     List<ApiErrorResponse.FieldError> fieldErrors) {
        ApiErrorResponse body = ApiErrorResponse.builder()
                .timestamp(LocalDateTime.now())
                .status(status.value())
                .error(errorCode)
                .message(message)
                .path(request.getRequestURI())
                .fieldErrors(fieldErrors)
                .build();
        return ResponseEntity.status(status).body(body);
    }
}
