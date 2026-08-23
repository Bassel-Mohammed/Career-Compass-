package com.careercompass.controller;

import com.careercompass.dto.request.BookAppointmentRequest;
import com.careercompass.dto.response.AppointmentResponse;
import com.careercompass.dto.response.MentorSummaryResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.ConsultationService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Job Seeker mentor browsing + booking endpoints (FR-JS-24/25). Same `/api/job-seekers/me`
 * prefix and `@CurrentUser` pattern as the other job-seeker controllers.
 */
@RestController
@RequestMapping("/api/job-seekers/me")
@RequiredArgsConstructor
public class ConsultationController {

    private final ConsultationService consultationService;

    @GetMapping("/mentors")
    public ResponseEntity<List<MentorSummaryResponse>> listAvailableMentors(
            @CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(consultationService.listAvailableMentors(principal.getUserId()));
    }

    @PostMapping("/appointments")
    public ResponseEntity<AppointmentResponse> bookSession(
            @CurrentUser UserPrincipal principal, @Valid @RequestBody BookAppointmentRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(consultationService.bookSession(principal.getUserId(), request));
    }

    @GetMapping("/appointments")
    public ResponseEntity<List<AppointmentResponse>> listMyAppointments(
            @CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(consultationService.listMyAppointments(principal.getUserId()));
    }
}
