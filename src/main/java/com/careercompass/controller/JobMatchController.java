package com.careercompass.controller;

import com.careercompass.dto.response.JobMatchResult;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.JobMatchService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Job Seeker job-matching endpoint (FR-JS-23). Same `/api/job-seekers/me` prefix and
 * `@CurrentUser` pattern as the other job-seeker controllers. Recomputes fresh on every call
 * (same pattern as the skill dashboard, Increment 10) rather than serving a cached list —
 * see JobMatchService's Javadoc for the performance trade-off this implies.
 */
@RestController
@RequestMapping("/api/job-seekers/me/job-matches")
@RequiredArgsConstructor
public class JobMatchController {

    private final JobMatchService jobMatchService;

    @GetMapping
    public ResponseEntity<List<JobMatchResult>> getMyJobMatches(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(jobMatchService.matchJobSeekerToJobs(principal.getUserId()));
    }
}
