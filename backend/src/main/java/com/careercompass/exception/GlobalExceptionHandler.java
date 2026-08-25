package com.careercompass.exception;

import com.careercompass.dto.response.ApiErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

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

    /**
     * The AI service failed in a way the integration layer already understood and classified.
     * Answering with its chosen status keeps "the AI service is down" (503) distinct from "the
     * AI service sent us something invalid" (502) and from "it took too long" (504) — three
     * different operational problems that a single 500 would flatten into one.
     */
    @ExceptionHandler(AiServiceException.class)
    public ResponseEntity<ApiErrorResponse> handleAiService(AiServiceException ex,
                                                            HttpServletRequest request) {
        return build(ex.getStatus(), ex.getErrorCode(), ex.getMessage(), request, null);
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

    /**
     * Database constraints are the final guard for concurrent duplicate submissions and invalid
     * score writes. Return a controlled conflict without leaking SQL or constraint details.
     */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiErrorResponse> handleDataConflict(DataIntegrityViolationException ex,
                                                               HttpServletRequest request) {
        return build(HttpStatus.CONFLICT, "DATA_CONFLICT",
                "The requested change conflicts with data that was already saved. Refresh and try again.",
                request, null);
    }

    @ExceptionHandler(StaleResourceException.class)
    public ResponseEntity<ApiErrorResponse> handleStaleResource(StaleResourceException ex,
                                                                 HttpServletRequest request) {
        return build(HttpStatus.CONFLICT, "STALE_RESOURCE", ex.getMessage(), request, null);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiErrorResponse> handleUploadTooLarge(MaxUploadSizeExceededException ex,
                                                                  HttpServletRequest request) {
        return build(HttpStatus.PAYLOAD_TOO_LARGE, "FILE_TOO_LARGE",
                "The PDF exceeds the 10 MB upload limit.", request, null);
    }

    @ExceptionHandler({MissingServletRequestPartException.class,
            MissingServletRequestParameterException.class,
            HttpMessageNotReadableException.class})
    public ResponseEntity<ApiErrorResponse> handleMalformedRequest(Exception ex,
                                                                   HttpServletRequest request) {
        return build(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "A required request value is missing or malformed.", request, null);
    }

    /**
     * A wrong HTTP verb on an existing resource (e.g. PUT on a PATCH-only path) must not
     * fall into the catch-all 500: the client is told which part of the request is wrong.
     */
    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ApiErrorResponse> handleMethodNotSupported(
            HttpRequestMethodNotSupportedException ex, HttpServletRequest request) {
        return build(HttpStatus.METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED",
                "This endpoint does not support that HTTP method.", request, null);
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiErrorResponse> handleMediaTypeNotSupported(
            HttpMediaTypeNotSupportedException ex, HttpServletRequest request) {
        return build(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_MEDIA_TYPE",
                "Send this request with a supported Content-Type.", request, null);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiErrorResponse> handleTypeMismatch(
            MethodArgumentTypeMismatchException ex, HttpServletRequest request) {
        return build(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "A path or query parameter has an invalid value.", request, null);
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiErrorResponse> handleNotFound(ResourceNotFoundException ex,
                                                           HttpServletRequest request) {
        return build(HttpStatus.NOT_FOUND, "NOT_FOUND", ex.getMessage(), request, null);
    }

    /**
     * A request to a URL that matches no controller route at all (e.g. a client calling a
     * registration endpoint that deliberately does not exist for Administrators, Content
     * Managers, or Experts) is a 404, not a 500 — nothing went wrong on the server.
     *
     * This needs to be handled explicitly: Spring raises {@code NoResourceFoundException} for
     * an unmatched path, and because this class also declares a catch-all
     * {@code @ExceptionHandler(Exception.class)} below, without this method that catch-all
     * would swallow it and report every mistyped URL as an internal server error.
     * {@code NoHandlerFoundException} is included for the case where static-resource handling
     * is disabled (or {@code spring.mvc.throw-exception-if-no-handler-found} is enabled), in
     * which case that is the exception raised instead.
     */
    @ExceptionHandler({NoResourceFoundException.class, NoHandlerFoundException.class})
    public ResponseEntity<ApiErrorResponse> handleNoRouteFound(Exception ex,
                                                               HttpServletRequest request) {
        return build(HttpStatus.NOT_FOUND, "ENDPOINT_NOT_FOUND",
                "The requested endpoint does not exist.", request, null);
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
