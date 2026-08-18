package com.careercompass.controller;

import com.careercompass.dto.request.ConsultationOutcomeRequest;
import com.careercompass.dto.request.UpdateAvailabilityRequest;
import com.careercompass.dto.response.*;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.ExpertService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Expert self-service endpoints (FR-EX-02..12). Restricted to ROLE_EXPERT via SecurityConfig's
 * `/api/experts/**` path rule. Same `/me` + `@CurrentUser` pattern as the other actor
 * controllers.
 */
@RestController
@RequestMapping("/api/experts/me")
@RequiredArgsConstructor
public class ExpertController {

    private final ExpertService expertService;

    @GetMapping
    public ResponseEntity<ExpertResponse> getMyProfile(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(expertService.getProfile(principal.getUserId()));
    }

    @PatchMapping("/status/activate")
    public ResponseEntity<ExpertResponse> activate(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(expertService.updateStatus(principal.getUserId(), true));
    }

    @PatchMapping("/status/deactivate")
    public ResponseEntity<ExpertResponse> deactivate(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(expertService.updateStatus(principal.getUserId(), false));
    }

    @PutMapping("/availability")
    public ResponseEntity<List<AvailabilitySlotResponse>> updateAvailability(
            @CurrentUser UserPrincipal principal, @Valid @RequestBody UpdateAvailabilityRequest request) {
        return ResponseEntity.ok(expertService.updateAvailability(principal.getUserId(), request));
    }

    @GetMapping("/sessions/scheduled")
    public ResponseEntity<List<AppointmentResponse>> getScheduledSessions(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(expertService.getScheduledSessions(principal.getUserId()));
    }

    @GetMapping("/sessions/history")
    public ResponseEntity<List<AppointmentResponse>> getHistory(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(expertService.getConsultationHistory(principal.getUserId()));
    }

    @PatchMapping("/appointments/{appointmentId}/accept")
    public ResponseEntity<AppointmentResponse> accept(@CurrentUser UserPrincipal principal,
                                                         @PathVariable Integer appointmentId) {
        return ResponseEntity.ok(expertService.acceptRequest(principal.getUserId(), appointmentId));
    }

    @PatchMapping("/appointments/{appointmentId}/reject")
    public ResponseEntity<AppointmentResponse> reject(@CurrentUser UserPrincipal principal,
                                                         @PathVariable Integer appointmentId) {
        return ResponseEntity.ok(expertService.rejectRequest(principal.getUserId(), appointmentId));
    }

    @PatchMapping("/appointments/{appointmentId}/outcome")
    public ResponseEntity<AppointmentResponse> submitOutcome(
            @CurrentUser UserPrincipal principal, @PathVariable Integer appointmentId,
            @RequestBody ConsultationOutcomeRequest request) {
        return ResponseEntity.ok(expertService.submitConsultationOutcome(
                principal.getUserId(), appointmentId, request));
    }

    @GetMapping("/job-seekers/{jobseekerId}/skill-dashboard")
    public ResponseEntity<SkillDashboardResponse> viewJobSeekerSkillProfile(
            @CurrentUser UserPrincipal principal, @PathVariable Integer jobseekerId) {
        return ResponseEntity.ok(expertService.viewJobSeekerSkillProfile(principal.getUserId(), jobseekerId));
    }

    @GetMapping("/job-seekers/{jobseekerId}/course-recommendations")
    public ResponseEntity<List<CourseRecommendationItem>> viewJobSeekerRecommendations(
            @CurrentUser UserPrincipal principal, @PathVariable Integer jobseekerId) {
        return ResponseEntity.ok(
                expertService.viewJobSeekerRecommendedCourses(principal.getUserId(), jobseekerId));
    }
}
