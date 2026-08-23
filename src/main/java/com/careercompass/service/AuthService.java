package com.careercompass.service;

import com.careercompass.dto.request.LoginRequest;
import com.careercompass.dto.request.RegisterEmployerRequest;
import com.careercompass.dto.request.RegisterJobSeekerRequest;
import com.careercompass.dto.response.AuthResponse;
import com.careercompass.entity.Administrator;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.Employer;
import com.careercompass.entity.Expert;
import com.careercompass.entity.JobSeeker;
import com.careercompass.exception.EmailAlreadyExistsException;
import com.careercompass.exception.InvalidCredentialsException;
import com.careercompass.repository.AdministratorRepository;
import com.careercompass.repository.ContentManagerRepository;
import com.careercompass.repository.EmployerRepository;
import com.careercompass.repository.ExpertRepository;
import com.careercompass.repository.JobSeekerRepository;
import com.careercompass.security.Role;
import com.careercompass.security.jwt.JwtTokenProvider;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

/**
 * Business Layer service for authentication
 * (FR-JS-01/02/26/27, FR-EMP-01/02/14/15, FR-SA-01/11/12, FR-EX-01/13/14, FR-CM-01/6/7).
 *
 * Only Job Seeker and Employer support self-registration here, since those are the only two
 * actors with a public FR-xx-01 "register an account" requirement. Content Managers and
 * Experts are created BY an Administrator (FR-SA-02, FR-EX-01) — see
 * {@link ContentManagerAdminService} and {@link ExpertAdminService}. Administrators themselves
 * have no registration flow at all (see {@link #loginAdmin} Javadoc).
 */
@Service
@RequiredArgsConstructor
public class AuthService {

    private final JobSeekerRepository jobSeekerRepository;
    private final EmployerRepository employerRepository;
    private final AdministratorRepository administratorRepository;
    private final ExpertRepository expertRepository;
    private final ContentManagerRepository contentManagerRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;
    private final TokenRevocationService tokenRevocationService;

    @Transactional
    public AuthResponse registerJobSeeker(RegisterJobSeekerRequest request) {
        if (jobSeekerRepository.existsByEmail(request.getEmail())) {
            throw new EmailAlreadyExistsException(request.getEmail());
        }

        JobSeeker jobSeeker = JobSeeker.builder()
                .firstName(request.getFirstName())
                .lastName(request.getLastName())
                .email(request.getEmail())
                .passwordHash(passwordEncoder.encode(request.getPassword()))
                .build();

        jobSeeker = jobSeekerRepository.save(jobSeeker);

        return issueToken(jobSeeker.getJobseekerId(), jobSeeker.getEmail(), Role.JOB_SEEKER);
    }

    @Transactional
    public AuthResponse loginJobSeeker(LoginRequest request) {
        JobSeeker jobSeeker = jobSeekerRepository.findByEmail(request.getEmail())
                .orElseThrow(InvalidCredentialsException::new);

        if (!passwordEncoder.matches(request.getPassword(), jobSeeker.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }

        jobSeeker.setLastLoginAt(LocalDateTime.now());
        jobSeekerRepository.save(jobSeeker);

        return issueToken(jobSeeker.getJobseekerId(), jobSeeker.getEmail(), Role.JOB_SEEKER);
    }

    @Transactional
    public AuthResponse registerEmployer(RegisterEmployerRequest request) {
        if (employerRepository.existsByEmail(request.getEmail())) {
            throw new EmailAlreadyExistsException(request.getEmail());
        }

        Employer employer = Employer.builder()
                .companyName(request.getCompanyName())
                .industry(request.getIndustry())
                .email(request.getEmail())
                .passwordHash(passwordEncoder.encode(request.getPassword()))
                .companyDescription(request.getCompanyDescription())
                .build();

        employer = employerRepository.save(employer);

        return issueToken(employer.getEmployerId(), employer.getEmail(), Role.EMPLOYER);
    }

    @Transactional(readOnly = true)
    public AuthResponse loginEmployer(LoginRequest request) {
        Employer employer = employerRepository.findByEmail(request.getEmail())
                .orElseThrow(InvalidCredentialsException::new);

        if (!passwordEncoder.matches(request.getPassword(), employer.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }

        return issueToken(employer.getEmployerId(), employer.getEmail(), Role.EMPLOYER);
    }

    /**
     * FR-SA-01/11/12: Administrator login. No self-registration counterpart — Administrator
     * accounts are provisioned outside the application (e.g. a one-off seed/migration), not
     * created via any public or even admin-facing API endpoint, since exposing "create an
     * admin" as an API call (even behind auth) would be a privilege-escalation risk not
     * justified by any FR. This is a deliberate scope decision, noted in the increment doc.
     */
    @Transactional(readOnly = true)
    public AuthResponse loginAdmin(LoginRequest request) {
        Administrator administrator = administratorRepository.findByEmail(request.getEmail())
                .orElseThrow(InvalidCredentialsException::new);

        if (!passwordEncoder.matches(request.getPassword(), administrator.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }

        return issueToken(administrator.getAdminId(), administrator.getEmail(), Role.ADMIN);
    }

    /** FR-EX-01/13/14: Expert login. No self-registration counterpart — see class Javadoc. */
    @Transactional(readOnly = true)
    public AuthResponse loginExpert(LoginRequest request) {
        Expert expert = expertRepository.findByEmail(request.getEmail())
                .orElseThrow(InvalidCredentialsException::new);

        if (!passwordEncoder.matches(request.getPassword(), expert.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }

        return issueToken(expert.getExpertId(), expert.getEmail(), Role.EXPERT);
    }

    /** FR-CM-01/6/7: Content Manager login. No self-registration counterpart — see class Javadoc. */
    @Transactional(readOnly = true)
    public AuthResponse loginContentManager(LoginRequest request) {
        ContentManager contentManager = contentManagerRepository.findByEmail(request.getEmail())
                .orElseThrow(InvalidCredentialsException::new);

        if (!passwordEncoder.matches(request.getPassword(), contentManager.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }

        if (!Boolean.TRUE.equals(contentManager.getIsActive())) {
            throw new InvalidCredentialsException(); // deactivated accounts (FR-SA-05) cannot log in
        }

        return issueToken(contentManager.getContentManagerId(), contentManager.getEmail(), Role.CONTENT_MANAGER);
    }

    /**
     * FR-JS-03 / FR-CM-02 / FR-EMP-03 (plus Administrators and Experts): ends the session the
     * presented token represents, for whichever actor is calling.
     *
     * The token reaching this method has already been validated by JwtAuthFilter — the route
     * requires authentication — so it is known to be signed, unexpired and not already
     * revoked. All that remains is to record it as surrendered.
     */
    public void logout(String authorizationHeader) {
        String token = extractBearerToken(authorizationHeader);
        tokenRevocationService.revoke(token);
    }

    private String extractBearerToken(String authorizationHeader) {
        if (authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            // Not reachable through the secured route, but guarded rather than left to throw
            // a raw StringIndexOutOfBounds if the endpoint is ever exposed differently.
            throw new InvalidCredentialsException();
        }
        return authorizationHeader.substring("Bearer ".length()).trim();
    }

    private AuthResponse issueToken(Integer userId, String email, Role role) {
        String token = jwtTokenProvider.generateToken(userId, email, role);
        return AuthResponse.builder()
                .token(token)
                .tokenType("Bearer")
                .role(role.name())
                .userId(userId)
                .email(email)
                .expiresInSeconds(jwtTokenProvider.getExpirationSeconds())
                .build();
    }
}
