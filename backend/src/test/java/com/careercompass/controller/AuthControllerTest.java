package com.careercompass.controller;

import com.careercompass.config.SecurityConfig;
import com.careercompass.dto.request.LoginRequest;
import com.careercompass.dto.request.RegisterJobSeekerRequest;
import com.careercompass.dto.response.AuthResponse;
import com.careercompass.exception.EmailAlreadyExistsException;
import com.careercompass.exception.InvalidCredentialsException;
import com.careercompass.security.jwt.JwtAuthFilter;
import com.careercompass.security.jwt.JwtProperties;
import com.careercompass.security.jwt.JwtTokenProvider;
import com.careercompass.service.AuthService;
import com.careercompass.service.TokenRevocationService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Web-layer slice test for {@link AuthController} — verifies the actual HTTP request/response
 * contract for FR-JS-01/02 and FR-EMP-01/02, including validation and error-mapping behaviour,
 * with {@link AuthService} mocked out (this is NOT testing AuthService's own logic again —
 * that's AuthServiceTest's job — it's testing that the controller wires requests/responses and
 * error handling correctly).
 *
 * Uses {@code @WebMvcTest} so the REAL SecurityConfig/JwtAuthFilter/GlobalExceptionHandler run,
 * confirming `/api/auth/**` is genuinely public (no token required) end-to-end, not just
 * assumed from reading the config.
 *
 * `@WebMvcTest` only scans controller-layer beans by default — the security infrastructure
 * classes (`SecurityConfig`, `JwtAuthFilter`, `JwtTokenProvider`) are plain `@Component`/
 * `@Configuration` beans that need to be explicitly imported for this slice, and
 * `JwtProperties` (a `@ConfigurationProperties` class) needs `@EnableConfigurationProperties`
 * so its `careercompass.jwt.secret` value actually gets bound from application.yml rather
 * than staying null.
 */
@WebMvcTest(controllers = AuthController.class)
@Import({SecurityConfig.class, JwtAuthFilter.class, JwtTokenProvider.class})
@EnableConfigurationProperties(JwtProperties.class)
class AuthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private AuthService authService;

    // JwtAuthFilter is @Import-ed above as a REAL bean (see class Javadoc), and its
    // constructor now requires TokenRevocationService (added for logout). Without this
    // @MockBean, Spring cannot construct JwtAuthFilter in this slice — there is no JPA
    // context here to supply a real RevokedTokenRepository — and every test in this class
    // fails at context startup rather than at any assertion.
    @MockBean
    private TokenRevocationService tokenRevocationService;

    // Purpose: valid registration request returns 201 CREATED with a JWT in the response body.
    @Test
    void registerJobSeeker_withValidRequest_returns201WithToken() throws Exception {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setFirstName("Basil");
        request.setLastName("Mohammad");
        request.setEmail("basil@example.com");
        request.setPassword("StrongPass!");

        when(authService.registerJobSeeker(any())).thenReturn(AuthResponse.builder()
                .token("fake-jwt").tokenType("Bearer").role("JOB_SEEKER").userId(1)
                .email("basil@example.com").expiresInSeconds(1800).build());

        mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.token", is("fake-jwt")))
                .andExpect(jsonPath("$.role", is("JOB_SEEKER")));
    }

    // Purpose: registration with a blank email fails Bean Validation before ever reaching the
    // service layer, returning 400 with a field-level error (NFR-SEC-05: server-side input
    // validation).
    @Test
    void registerJobSeeker_withBlankEmail_returns400ValidationError() throws Exception {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setFirstName("Basil");
        request.setLastName("Mohammad");
        request.setEmail(""); // invalid
        request.setPassword("StrongPass!");

        mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("VALIDATION_ERROR")));
    }

    // Purpose: registration with a short password fails Bean Validation (min 8 characters).
    @Test
    void registerJobSeeker_withShortPassword_returns400ValidationError() throws Exception {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setFirstName("Basil");
        request.setLastName("Mohammad");
        request.setEmail("basil@example.com");
        request.setPassword("short"); // < 8 chars

        mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("VALIDATION_ERROR")));
    }

    // Purpose: length alone is insufficient; a numeric-only password is easy to guess and
    // must be rejected even when it contains eight characters.
    @Test
    void registerJobSeeker_withNumericOnlyPassword_returns400ValidationError() throws Exception {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setFirstName("Basil");
        request.setLastName("Mohammad");
        request.setEmail("basil@example.com");
        request.setPassword("12345678");

        mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("VALIDATION_ERROR")));
    }

    // Purpose: registering with an email that's already taken surfaces the service's
    // EmailAlreadyExistsException as a 409 CONFLICT through the real GlobalExceptionHandler.
    @Test
    void registerJobSeeker_withDuplicateEmail_returns409() throws Exception {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setFirstName("Basil");
        request.setLastName("Mohammad");
        request.setEmail("taken@example.com");
        request.setPassword("StrongPass!");

        when(authService.registerJobSeeker(any()))
                .thenThrow(new EmailAlreadyExistsException("taken@example.com"));

        mockMvc.perform(post("/api/auth/job-seekers/register")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error", is("EMAIL_ALREADY_EXISTS")));
    }

    // Purpose: valid login returns 200 with a JWT.
    @Test
    void loginJobSeeker_withValidCredentials_returns200WithToken() throws Exception {
        LoginRequest request = new LoginRequest();
        request.setEmail("basil@example.com");
        request.setPassword("password123");

        when(authService.loginJobSeeker(any())).thenReturn(AuthResponse.builder()
                .token("fake-jwt").tokenType("Bearer").role("JOB_SEEKER").userId(1)
                .email("basil@example.com").expiresInSeconds(1800).build());

        mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token", is("fake-jwt")));
    }

    // Purpose: wrong credentials surface as 401 UNAUTHORIZED with a generic message, never
    // revealing whether the email exists or the password was wrong.
    @Test
    void loginJobSeeker_withWrongPassword_returns401() throws Exception {
        LoginRequest request = new LoginRequest();
        request.setEmail("basil@example.com");
        request.setPassword("wrongPassword");

        when(authService.loginJobSeeker(any())).thenThrow(new InvalidCredentialsException());

        mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error", is("INVALID_CREDENTIALS")));
    }

    // Purpose: login with a malformed email fails validation before hitting the service.
    @Test
    void loginJobSeeker_withMalformedEmail_returns400() throws Exception {
        LoginRequest request = new LoginRequest();
        request.setEmail("not-an-email");
        request.setPassword("password123");

        mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error", is("VALIDATION_ERROR")));
    }

    // Purpose: /api/auth/** endpoints are genuinely public — no Authorization header is
    // required to reach them, confirmed by hitting the real SecurityConfig filter chain
    // rather than assuming it from the config alone.
    @Test
    void authEndpoints_areAccessibleWithoutAuthentication() throws Exception {
        LoginRequest request = new LoginRequest();
        request.setEmail("basil@example.com");
        request.setPassword("password123");

        when(authService.loginJobSeeker(any())).thenReturn(AuthResponse.builder()
                .token("fake-jwt").build());

        // No Authorization header attached at all.
        mockMvc.perform(post("/api/auth/job-seekers/login")
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());
    }
}
