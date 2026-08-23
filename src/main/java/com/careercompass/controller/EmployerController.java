package com.careercompass.controller;

import com.careercompass.dto.request.JobPostRequest;
import com.careercompass.dto.request.UpdateEmployerProfileRequest;
import com.careercompass.dto.response.CandidateMatchResult;
import com.careercompass.dto.response.EmployerProfileResponse;
import com.careercompass.dto.response.JobResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.EmployerService;
import com.careercompass.service.JobMatchService;
import com.careercompass.service.JobService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Employer self-service endpoints (FR-EMP-05..10). Restricted to ROLE_EMPLOYER via
 * SecurityConfig's `/api/employers/**` path rule. Follows the same `/me` pattern as
 * JobSeekerController (Increment 7) for profile actions; job endpoints additionally enforce
 * per-resource ownership in JobService (an employer role alone isn't enough — it must be
 * THIS employer's job).
 */
@RestController
@RequestMapping("/api/employers")
@RequiredArgsConstructor
public class EmployerController {

    private final EmployerService employerService;
    private final JobService jobService;
    private final JobMatchService jobMatchService;

    // --- Company profile (FR-EMP-05/06) --------------------------------------------------

    @GetMapping("/me")
    public ResponseEntity<EmployerProfileResponse> getMyProfile(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(employerService.getProfile(principal.getUserId()));
    }

    @PutMapping("/me")
    public ResponseEntity<EmployerProfileResponse> updateMyProfile(
            @CurrentUser UserPrincipal principal,
            @Valid @RequestBody UpdateEmployerProfileRequest request) {
        return ResponseEntity.ok(employerService.updateProfile(principal.getUserId(), request));
    }

    // --- Job postings (FR-EMP-07/08/09/10) ------------------------------------------------

    @PostMapping("/me/jobs")
    public ResponseEntity<JobResponse> postJob(@CurrentUser UserPrincipal principal,
                                                 @Valid @RequestBody JobPostRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(jobService.postJob(principal.getUserId(), request));
    }

    @PutMapping("/me/jobs/{jobId}")
    public ResponseEntity<JobResponse> updateJob(@CurrentUser UserPrincipal principal,
                                                   @PathVariable Integer jobId,
                                                   @Valid @RequestBody JobPostRequest request) {
        return ResponseEntity.ok(jobService.updateJob(principal.getUserId(), jobId, request));
    }

    @DeleteMapping("/me/jobs/{jobId}")
    public ResponseEntity<Void> deleteJob(@CurrentUser UserPrincipal principal,
                                            @PathVariable Integer jobId) {
        jobService.deleteJob(principal.getUserId(), jobId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/me/jobs")
    public ResponseEntity<List<JobResponse>> listMyJobs(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(jobService.listMyJobs(principal.getUserId()));
    }

    // --- Matched candidates (FR-EMP-11/12) -------------------------------------------------

    @GetMapping("/me/jobs/{jobId}/candidates")
    public ResponseEntity<List<CandidateMatchResult>> getMatchedCandidates(
            @CurrentUser UserPrincipal principal, @PathVariable Integer jobId) {
        return ResponseEntity.ok(jobMatchService.matchCandidatesForJob(principal.getUserId(), jobId));
    }
}
