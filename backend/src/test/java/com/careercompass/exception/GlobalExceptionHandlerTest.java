package com.careercompass.exception;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Slice test for {@link GlobalExceptionHandler}, exercised through a minimal throwaway
 * controller ({@link ThrowingTestController}) that deliberately triggers each custom
 * exception. This verifies the actual HTTP status code and {@code ApiErrorResponse} JSON
 * shape produced for every error scenario the application defines, in one place — rather than
 * re-testing the same exception-handling behaviour separately inside every real controller's
 * test.
 *
 * Security is disabled for this slice (`@WithMockUser` / permitAll via test config) since the
 * exception mapping itself, not authentication, is what's under test here.
 */
@WebMvcTest(controllers = GlobalExceptionHandlerTest.ThrowingTestController.class)
@AutoConfigureMockMvc(addFilters = false)
@ContextConfiguration(classes = {
        GlobalExceptionHandlerTest.ThrowingTestController.class,
        GlobalExceptionHandler.class
})
class GlobalExceptionHandlerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    // Purpose: EmailAlreadyExistsException maps to 409 CONFLICT with the correct error code.
    @Test
    @WithMockUser
    void emailAlreadyExists_returns409WithErrorCode() throws Exception {
        mockMvc.perform(post("/test/email-exists"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status", is(409)))
                .andExpect(jsonPath("$.error", is("EMAIL_ALREADY_EXISTS")))
                .andExpect(jsonPath("$.message").exists())
                .andExpect(jsonPath("$.timestamp").exists());
    }

    // Purpose: InvalidCredentialsException maps to 401 UNAUTHORIZED with a generic message
    // (never reveals whether the email or the password was wrong).
    @Test
    @WithMockUser
    void invalidCredentials_returns401WithGenericMessage() throws Exception {
        mockMvc.perform(post("/test/invalid-credentials"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status", is(401)))
                .andExpect(jsonPath("$.error", is("INVALID_CREDENTIALS")))
                .andExpect(jsonPath("$.message", is("Invalid email or password.")));
    }

    // Purpose: ResourceNotFoundException maps to 404 NOT_FOUND.
    @Test
    @WithMockUser
    void resourceNotFound_returns404() throws Exception {
        mockMvc.perform(post("/test/not-found"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status", is(404)))
                .andExpect(jsonPath("$.error", is("NOT_FOUND")));
    }

    // Purpose: UnauthorizedActionException maps to 403 FORBIDDEN (distinct from a plain 401 —
    // the caller IS authenticated, they just don't own the resource).
    @Test
    @WithMockUser
    void unauthorizedAction_returns403() throws Exception {
        mockMvc.perform(post("/test/forbidden"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status", is(403)))
                .andExpect(jsonPath("$.error", is("FORBIDDEN")));
    }

    // Purpose: DuplicateResourceException maps to 409 CONFLICT.
    @Test
    @WithMockUser
    void duplicateResource_returns409() throws Exception {
        mockMvc.perform(post("/test/duplicate"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status", is(409)))
                .andExpect(jsonPath("$.error", is("DUPLICATE_RESOURCE")));
    }

    // Purpose: A constraint race maps to a controlled 409 without exposing SQL details.
    @Test
    @WithMockUser
    void dataIntegrityViolation_returns409WithoutLeakingConstraintDetails() throws Exception {
        mockMvc.perform(post("/test/data-conflict"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status", is(409)))
                .andExpect(jsonPath("$.error", is("DATA_CONFLICT")))
                .andExpect(jsonPath("$.message", is(
                        "The requested change conflicts with data that was already saved. "
                                + "Refresh and try again.")));
    }

    // Purpose: PrerequisiteNotMetException maps to 400 BAD_REQUEST (well-formed request, but
    // the account/data isn't in the right state yet — e.g. no career path selected).
    @Test
    @WithMockUser
    void prerequisiteNotMet_returns400() throws Exception {
        mockMvc.perform(post("/test/prerequisite-not-met"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status", is(400)))
                .andExpect(jsonPath("$.error", is("PREREQUISITE_NOT_MET")));
    }

    // Purpose: IllegalArgumentException (e.g. non-PDF file upload) maps to 400 BAD_REQUEST.
    @Test
    @WithMockUser
    void illegalArgument_returns400() throws Exception {
        mockMvc.perform(post("/test/illegal-argument"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status", is(400)))
                .andExpect(jsonPath("$.error", is("INVALID_REQUEST")));
    }

    // Purpose: IllegalStateException (e.g. AI service returned no usable data) maps to 502
    // BAD_GATEWAY, distinguishing an upstream-AI problem from a client mistake.
    @Test
    @WithMockUser
    void illegalState_returns502() throws Exception {
        mockMvc.perform(post("/test/illegal-state"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.status", is(502)))
                .andExpect(jsonPath("$.error", is("AI_SERVICE_RESPONSE_INVALID")));
    }

    // Purpose: Bean Validation failures (@Valid on a request body) map to 400 BAD_REQUEST
    // with per-field error details in fieldErrors, satisfying NFR-USE-03 (clear, actionable
    // error messages) — the response tells the client exactly which field was invalid and why.
    @Test
    @WithMockUser
    void validationFailure_returns400WithFieldErrors() throws Exception {
        TestRequestBody invalidBody = new TestRequestBody();
        invalidBody.setName(""); // blank, violates @NotBlank

        mockMvc.perform(post("/test/validate")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(invalidBody)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status", is(400)))
                .andExpect(jsonPath("$.error", is("VALIDATION_ERROR")))
                .andExpect(jsonPath("$.fieldErrors[0].field", is("name")));
    }

    // Purpose: Any other uncaught exception maps to a generic 500 that never leaks internal
    // details (e.g. a stack trace or exception class name) to the client.
    @Test
    @WithMockUser
    void unexpectedException_returns500WithoutLeakingDetails() throws Exception {
        mockMvc.perform(post("/test/unexpected"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status", is(500)))
                .andExpect(jsonPath("$.error", is("INTERNAL_ERROR")))
                .andExpect(jsonPath("$.message").value(
                        org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("Exception"))));
    }

    /** Minimal controller that exists only to deliberately trigger each exception type. */
    @RestController
    static class ThrowingTestController {

        @PostMapping("/test/email-exists")
        void emailExists() {
            throw new EmailAlreadyExistsException("taken@example.com");
        }

        @PostMapping("/test/invalid-credentials")
        void invalidCredentials() {
            throw new InvalidCredentialsException();
        }

        @PostMapping("/test/not-found")
        void notFound() {
            throw new ResourceNotFoundException("Thing with id 1 not found.");
        }

        @PostMapping("/test/forbidden")
        void forbidden() {
            throw new UnauthorizedActionException("Not your resource.");
        }

        @PostMapping("/test/duplicate")
        void duplicate() {
            throw new DuplicateResourceException("Already exists.");
        }

        @PostMapping("/test/data-conflict")
        void dataConflict() {
            throw new DataIntegrityViolationException(
                    "Duplicate entry for constraint uq_quiz_response_question");
        }

        @PostMapping("/test/prerequisite-not-met")
        void prerequisiteNotMet() {
            throw new PrerequisiteNotMetException("Select a career path first.");
        }

        @PostMapping("/test/illegal-argument")
        void illegalArgument() {
            throw new IllegalArgumentException("Only PDF files are accepted.");
        }

        @PostMapping("/test/illegal-state")
        void illegalState() {
            throw new IllegalStateException("AI service returned no usable data.");
        }

        @PostMapping("/test/validate")
        void validate(@Valid @RequestBody TestRequestBody body) {
            // no-op — reaching here means validation passed
        }

        @PostMapping("/test/unexpected")
        void unexpected() {
            throw new RuntimeException("boom");
        }
    }

    @Getter
    @Setter
    static class TestRequestBody {
        @NotBlank(message = "name is required")
        private String name;
    }
}
