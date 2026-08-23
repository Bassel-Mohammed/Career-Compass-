package com.careercompass.controller;

import com.careercompass.dto.request.UpdateJobSeekerProfileRequest;
import com.careercompass.dto.response.JobSeekerProfileResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.JobSeekerService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Job Seeker self-service endpoints (FR-JS-06/07/08/09). Restricted to ROLE_JOB_SEEKER via
 * SecurityConfig's `/api/job-seekers/**` path rule.
 *
 * Uses "/me" rather than "/{id}" deliberately — the acting job seeker is always the one
 * embedded in their own JWT (see {@link CurrentUser}'s Javadoc), never a client-supplied id.
 */
@RestController
@RequestMapping("/api/job-seekers")
@RequiredArgsConstructor
public class JobSeekerController {

    private final JobSeekerService jobSeekerService;

    @GetMapping("/me")
    public ResponseEntity<JobSeekerProfileResponse> getMyProfile(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(jobSeekerService.getProfile(principal.getUserId()));
    }

    @PutMapping("/me")
    public ResponseEntity<JobSeekerProfileResponse> updateMyProfile(
            @CurrentUser UserPrincipal principal,
            @Valid @RequestBody UpdateJobSeekerProfileRequest request) {
        return ResponseEntity.ok(jobSeekerService.updateProfile(principal.getUserId(), request));
    }

    @DeleteMapping("/me")
    public ResponseEntity<Void> deleteMyProfile(@CurrentUser UserPrincipal principal) {
        jobSeekerService.deleteProfile(principal.getUserId());
        return ResponseEntity.noContent().build();
    }
}
