package com.careercompass.controller;

import com.careercompass.dto.request.ConfirmTranscriptRequest;
import com.careercompass.dto.response.SkillDashboardResponse;
import com.careercompass.integration.dto.CareerPathSkillsResponse;
import com.careercompass.dto.response.TranscriptReviewResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.TranscriptService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * Job Seeker transcript + skill dashboard endpoints (FR-JS-10..14, FR-JS-21).
 * Nested under `/api/job-seekers/me/**` — still restricted to ROLE_JOB_SEEKER via
 * SecurityConfig's `/api/job-seekers/**` rule, and still resolves the acting job seeker from
 * `@CurrentUser`, same pattern as JobSeekerController (Increment 7).
 */
@RestController
@RequestMapping("/api/job-seekers/me")
@RequiredArgsConstructor
public class TranscriptController {

    private final TranscriptService transcriptService;

    /** FR-JS-10: upload transcript PDF for extraction/review (nothing persisted yet). */
    @PostMapping(value = "/transcript", consumes = "multipart/form-data")
    public ResponseEntity<TranscriptReviewResponse> uploadTranscript(
            @CurrentUser UserPrincipal principal,
            @RequestParam("file") MultipartFile file) {
        return ResponseEntity.ok(transcriptService.uploadAndExtract(principal.getUserId(), file));
    }

    /** FR-JS-11: confirm the reviewed rows, persist, and compute the skill dashboard. */
    @PostMapping("/transcript/confirm")
    public ResponseEntity<SkillDashboardResponse> confirmTranscript(
            @CurrentUser UserPrincipal principal,
            @Valid @RequestBody ConfirmTranscriptRequest request) {
        return ResponseEntity.ok(transcriptService.confirmTranscript(principal.getUserId(), request));
    }

    /** FR-JS-14/21: current skill dashboard. */
    @GetMapping("/skill-dashboard")
    public ResponseEntity<SkillDashboardResponse> getSkillDashboard(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(transcriptService.getSkillDashboard(principal.getUserId()));
    }

    /**
     * What the selected career path asks for, derived from job postings.
     *
     * <p>Needs a career path but not a transcript, which is the whole point: it is the one thing
     * the dashboard can show truthfully before a student has uploaded anything.
     */
    @GetMapping("/career-path/skills")
    public ResponseEntity<CareerPathSkillsResponse> getCareerPathSkills(
            @CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(transcriptService.getCareerPathSkills(principal.getUserId()));
    }
}
