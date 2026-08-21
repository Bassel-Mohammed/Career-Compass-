package com.careercompass.controller;

import com.careercompass.dto.request.LoginRequest;
import com.careercompass.dto.request.RegisterEmployerRequest;
import com.careercompass.dto.request.RegisterJobSeekerRequest;
import com.careercompass.dto.response.AuthResponse;
import com.careercompass.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Public authentication endpoints (FR-JS-01/02, FR-EMP-01/02).
 * All endpoints under /api/auth/** are permitAll in SecurityConfig.
 */
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/job-seekers/register")
    public ResponseEntity<AuthResponse> registerJobSeeker(@Valid @RequestBody RegisterJobSeekerRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(authService.registerJobSeeker(request));
    }

    @PostMapping("/job-seekers/login")
    public ResponseEntity<AuthResponse> loginJobSeeker(@Valid @RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.loginJobSeeker(request));
    }

    @PostMapping("/employers/register")
    public ResponseEntity<AuthResponse> registerEmployer(@Valid @RequestBody RegisterEmployerRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(authService.registerEmployer(request));
    }

    @PostMapping("/employers/login")
    public ResponseEntity<AuthResponse> loginEmployer(@Valid @RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.loginEmployer(request));
    }

    /**
     * FR-SA-01: Administrator login. No corresponding /register endpoint — see
     * {@link com.careercompass.service.AuthService#loginAdmin} Javadoc for why.
     */
    @PostMapping("/admins/login")
    public ResponseEntity<AuthResponse> loginAdmin(@Valid @RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.loginAdmin(request));
    }

    /** FR-EX-01: Expert login. No corresponding /register endpoint — see AuthService.loginExpert Javadoc. */
    @PostMapping("/experts/login")
    public ResponseEntity<AuthResponse> loginExpert(@Valid @RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.loginExpert(request));
    }

    /** FR-CM-01: Content Manager login. No corresponding /register endpoint — see AuthService Javadoc. */
    @PostMapping("/content-managers/login")
    public ResponseEntity<AuthResponse> loginContentManager(@Valid @RequestBody LoginRequest request) {
        return ResponseEntity.ok(authService.loginContentManager(request));
    }

    /**
     * FR-JS-03, FR-CM-02, FR-EMP-03 (and the equivalent for Administrators and Experts):
     * log out, ending the session the presented token represents.
     *
     * One endpoint serves all five actors, unlike login and registration. Those differ per
     * actor because each looks up a different table and accepts a different body; logging out
     * needs neither — the token already says who is calling — so splitting it five ways would
     * duplicate the same code behind five URLs.
     *
     * The token is added to a denylist rather than simply forgotten by the client, so that a
     * copy taken before logout cannot continue to be used for the remainder of its lifetime.
     * Returns 204 NO CONTENT: the session is gone and there is nothing meaningful to return.
     */
    @PostMapping("/logout")
    public ResponseEntity<Void> logout(@RequestHeader("Authorization") String authorizationHeader) {
        authService.logout(authorizationHeader);
        return ResponseEntity.noContent().build();
    }
}
