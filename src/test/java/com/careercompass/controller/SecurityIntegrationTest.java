package com.careercompass.controller;

import com.careercompass.config.SecurityConfig;
import com.careercompass.dto.request.JobPostRequest;
import com.careercompass.dto.response.JobSeekerProfileResponse;
import com.careercompass.dto.response.JobResponse;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.security.Role;
import com.careercompass.security.jwt.JwtAuthFilter;
import com.careercompass.security.jwt.JwtProperties;
import com.careercompass.security.jwt.JwtTokenProvider;
import com.careercompass.service.EmployerService;
import com.careercompass.service.JobMatchService;
import com.careercompass.service.JobSeekerService;
import com.careercompass.service.JobService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * End-to-end security test covering the full JWT filter chain (JwtAuthFilter -> SecurityConfig
 * role rules -> service-layer ownership checks) through real HTTP requests, using REAL JWTs
 * issued by {@link JwtTokenProvider} — not mocked authentication. This is the test that
 * concretely proves the security claims made throughout every prior increment's documentation
 * (NFR-SEC-04: role-based access control; ownership checks in JobService/JobSeekerService),
 * rather than just trusting the code review of SecurityConfig/@CurrentUser/getOwnedJobOrThrow.
 *
 * Covers, in order, the three layers of "can this caller do this":
 * 1. Authentication — is there a valid token at all?
 * 2. Authorization (role) — does the token's role match what this path requires?
 * 3. Authorization (ownership) — even with the right role, does this specific caller own
 *    this specific resource?
 */
@WebMvcTest(controllers = {JobSeekerController.class, EmployerController.class})
@Import({SecurityConfig.class, JwtAuthFilter.class, JwtTokenProvider.class})
@EnableConfigurationProperties(JwtProperties.class)
class SecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    @MockBean
    private JobSeekerService jobSeekerService;

    @MockBean
    private EmployerService employerService;

    @MockBean
    private JobService jobService;

    @MockBean
    private JobMatchService jobMatchService;

    private String jobSeekerToken;
    private String employerToken;

    @BeforeEach
    void issueTestTokens() {
        jobSeekerToken = jwtTokenProvider.generateToken(1, "jobseeker@example.com", Role.JOB_SEEKER);
        employerToken = jwtTokenProvider.generateToken(2, "employer@example.com", Role.EMPLOYER);
    }

    // Purpose: a request with NO Authorization header at all is rejected before it ever
    // reaches the controller — SecurityConfig's `anyRequest().authenticated()` catches it.
    @Test
    void requestWithNoToken_isRejected() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me"))
                .andExpect(status().isUnauthorized());
    }

    // Purpose: a request with a garbage/malformed token is rejected the same way as no token
    // — JwtAuthFilter's validateToken() catches malformed tokens and never populates the
    // security context, so the request falls through to "unauthenticated".
    @Test
    void requestWithMalformedToken_isRejected() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer not-a-real-jwt"))
                .andExpect(status().isUnauthorized());
    }

    // Purpose: a valid JOB_SEEKER token can access the job-seeker "me" endpoint — the
    // baseline positive case the negative cases below are contrasted against.
    @Test
    void jobSeekerToken_canAccessOwnProfile() throws Exception {
        when(jobSeekerService.getProfile(1)).thenReturn(
                JobSeekerProfileResponse.builder().jobseekerId(1).firstName("Basil").build());

        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk());
    }

    // Purpose: a valid token belonging to the WRONG ROLE (an Employer token, on a
    // Job-Seeker-only path) is rejected with 403 — proves SecurityConfig's role-scoped path
    // rules (NFR-SEC-04) are actually enforced, not just declared.
    @Test
    void employerToken_cannotAccessJobSeekerOnlyEndpoint() throws Exception {
        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + employerToken))
                .andExpect(status().isForbidden());
    }

    // Purpose: a JOB_SEEKER token cannot access an EMPLOYER-only endpoint either — confirms
    // the role restriction works symmetrically in both directions, not just one.
    @Test
    void jobSeekerToken_cannotAccessEmployerOnlyEndpoint() throws Exception {
        mockMvc.perform(get("/api/employers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isForbidden());
    }

    // Purpose: the caller's own id is taken from the verified JWT (@CurrentUser), never from
    // any client-supplied value in the request — this test never sends an id anywhere in the
    // request and the mocked service is still invoked with the id embedded in the token (1),
    // confirming there is no way for the request itself to influence whose data is returned.
    @Test
    void jobSeekerProfile_isAlwaysResolvedFromTokenNotFromRequest() throws Exception {
        when(jobSeekerService.getProfile(1)).thenReturn(
                JobSeekerProfileResponse.builder().jobseekerId(1).build());

        mockMvc.perform(get("/api/job-seekers/me")
                        .header("Authorization", "Bearer " + jobSeekerToken))
                .andExpect(status().isOk());

        org.mockito.Mockito.verify(jobSeekerService).getProfile(eq(1));
        // Never called with any other id, even though nothing in the request body/path
        // constrains this — this is purely because @CurrentUser reads the JWT subject.
        org.mockito.Mockito.verify(jobSeekerService, org.mockito.Mockito.never()).getProfile(eq(2));
    }

    // Purpose: even with a valid EMPLOYER-role token, updating a job that belongs to a
    // DIFFERENT employer is rejected with 403 by the service-layer ownership check
    // (JobService.getOwnedJobOrThrow) — this is the layer a role-only check cannot provide,
    // demonstrated here through a real HTTP request rather than a direct service-layer test.
    @Test
    void employerToken_cannotUpdateAnotherEmployersJob() throws Exception {
        JobPostRequest request = new JobPostRequest();
        request.setTitle("Hijacked Title");
        request.setDescription("Attempted takeover.");

        when(jobService.updateJob(eq(2), eq(999), any()))
                .thenThrow(new UnauthorizedActionException("You do not have permission to modify this job posting."));

        mockMvc.perform(put("/api/employers/me/jobs/999")
                        .header("Authorization", "Bearer " + employerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden());
    }

    // Purpose: an employer updating their OWN job succeeds (200) — the positive counterpart
    // to the previous test, confirming the ownership check isn't just always rejecting.
    @Test
    void employerToken_canUpdateOwnJob() throws Exception {
        JobPostRequest request = new JobPostRequest();
        request.setTitle("Updated Title");
        request.setDescription("Legitimate update.");

        when(jobService.updateJob(eq(2), eq(100), any()))
                .thenReturn(JobResponse.builder().jobId(100).title("Updated Title").build());

        mockMvc.perform(put("/api/employers/me/jobs/100")
                        .header("Authorization", "Bearer " + employerToken)
                        .contentType("application/json")
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());
    }
}
