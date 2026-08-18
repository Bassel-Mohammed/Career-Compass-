package com.careercompass.service;

import com.careercompass.dto.request.LoginRequest;
import com.careercompass.dto.request.RegisterJobSeekerRequest;
import com.careercompass.dto.response.AuthResponse;
import com.careercompass.entity.JobSeeker;
import com.careercompass.exception.EmailAlreadyExistsException;
import com.careercompass.exception.InvalidCredentialsException;
import com.careercompass.repository.EmployerRepository;
import com.careercompass.repository.JobSeekerRepository;
import com.careercompass.security.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

/**
 * Unit tests for AuthService's job-seeker flows, with repositories/encoder/token-provider
 * mocked (Mockito) — no Spring context, no database, per NFR-MNT-07.
 */
@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock
    private JobSeekerRepository jobSeekerRepository;

    @Mock
    private EmployerRepository employerRepository;

    @Mock
    private com.careercompass.repository.AdministratorRepository administratorRepository;

    @Mock
    private com.careercompass.repository.ExpertRepository expertRepository;

    @Mock
    private com.careercompass.repository.ContentManagerRepository contentManagerRepository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private JwtTokenProvider jwtTokenProvider;

    @InjectMocks
    private AuthService authService;

    // Purpose: Register Job Seeker - saves Hashed Password And Returns Token.
    @Test
    void registerJobSeeker_savesHashedPasswordAndReturnsToken() {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setFirstName("Basil");
        request.setLastName("Mohammad");
        request.setEmail("basil@example.com");
        request.setPassword("plainPassword123");

        when(jobSeekerRepository.existsByEmail("basil@example.com")).thenReturn(false);
        when(passwordEncoder.encode("plainPassword123")).thenReturn("hashed-password");
        when(jobSeekerRepository.save(any(JobSeeker.class))).thenAnswer(invocation -> {
            JobSeeker js = invocation.getArgument(0);
            js.setJobseekerId(1);
            return js;
        });
        when(jwtTokenProvider.generateToken(eq(1), eq("basil@example.com"), any()))
                .thenReturn("fake-jwt-token");
        when(jwtTokenProvider.getExpirationSeconds()).thenReturn(1800L);

        AuthResponse response = authService.registerJobSeeker(request);

        assertThat(response.getToken()).isEqualTo("fake-jwt-token");
        assertThat(response.getUserId()).isEqualTo(1);
        assertThat(response.getRole()).isEqualTo("JOB_SEEKER");

        // Confirm the raw password was never persisted — only the encoder's output was.
        verify(passwordEncoder).encode("plainPassword123");
        verify(jobSeekerRepository).save(argThat(js -> js.getPasswordHash().equals("hashed-password")));
    }

    // Purpose: Register Job Seeker - throws When Email Already Exists.
    @Test
    void registerJobSeeker_throwsWhenEmailAlreadyExists() {
        RegisterJobSeekerRequest request = new RegisterJobSeekerRequest();
        request.setEmail("taken@example.com");
        request.setFirstName("A");
        request.setLastName("B");
        request.setPassword("password123");

        when(jobSeekerRepository.existsByEmail("taken@example.com")).thenReturn(true);

        assertThatThrownBy(() -> authService.registerJobSeeker(request))
                .isInstanceOf(EmailAlreadyExistsException.class);

        verify(jobSeekerRepository, never()).save(any());
    }

    // Purpose: Login Job Seeker - throws Invalid Credentials When Email Not Found.
    @Test
    void loginJobSeeker_throwsInvalidCredentialsWhenEmailNotFound() {
        LoginRequest request = new LoginRequest();
        request.setEmail("nobody@example.com");
        request.setPassword("whatever");

        when(jobSeekerRepository.findByEmail("nobody@example.com")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> authService.loginJobSeeker(request))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    // Purpose: Login Job Seeker - throws Invalid Credentials When Password Does Not Match.
    @Test
    void loginJobSeeker_throwsInvalidCredentialsWhenPasswordDoesNotMatch() {
        LoginRequest request = new LoginRequest();
        request.setEmail("basil@example.com");
        request.setPassword("wrongPassword");

        JobSeeker existing = JobSeeker.builder()
                .jobseekerId(1)
                .email("basil@example.com")
                .passwordHash("correct-hash")
                .build();

        when(jobSeekerRepository.findByEmail("basil@example.com")).thenReturn(Optional.of(existing));
        when(passwordEncoder.matches("wrongPassword", "correct-hash")).thenReturn(false);

        assertThatThrownBy(() -> authService.loginJobSeeker(request))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    // Purpose: Login Job Seeker - succeeds And Updates Last Login At.
    @Test
    void loginJobSeeker_succeedsAndUpdatesLastLoginAt() {
        LoginRequest request = new LoginRequest();
        request.setEmail("basil@example.com");
        request.setPassword("correctPassword");

        JobSeeker existing = JobSeeker.builder()
                .jobseekerId(1)
                .email("basil@example.com")
                .passwordHash("correct-hash")
                .build();

        when(jobSeekerRepository.findByEmail("basil@example.com")).thenReturn(Optional.of(existing));
        when(passwordEncoder.matches("correctPassword", "correct-hash")).thenReturn(true);
        when(jobSeekerRepository.save(any(JobSeeker.class))).thenReturn(existing);
        when(jwtTokenProvider.generateToken(eq(1), eq("basil@example.com"), any()))
                .thenReturn("fake-jwt-token");
        when(jwtTokenProvider.getExpirationSeconds()).thenReturn(1800L);

        AuthResponse response = authService.loginJobSeeker(request);

        assertThat(response.getToken()).isEqualTo("fake-jwt-token");
        assertThat(existing.getLastLoginAt()).isNotNull();
        verify(jobSeekerRepository).save(existing);
    }
}
