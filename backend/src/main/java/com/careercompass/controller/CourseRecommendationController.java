package com.careercompass.controller;

import com.careercompass.dto.response.CourseRecommendationItem;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.CourseRecommendationService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Job Seeker course recommendation endpoints (FR-JS-15/16). Same `/api/job-seekers/me`
 * prefix and `@CurrentUser` pattern as JobSeekerController/TranscriptController.
 */
@RestController
@RequestMapping("/api/job-seekers/me/course-recommendations")
@RequiredArgsConstructor
public class CourseRecommendationController {

    private final CourseRecommendationService courseRecommendationService;

    /** (Re)generate recommendations from the job seeker's current weak skills. */
    @PostMapping("/generate")
    public ResponseEntity<List<CourseRecommendationItem>> generateRecommendations(
            @CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(courseRecommendationService.generateRecommendations(principal.getUserId()));
    }

    /** View previously generated recommendations. */
    @GetMapping
    public ResponseEntity<List<CourseRecommendationItem>> listRecommendations(
            @CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(courseRecommendationService.listStoredRecommendations(principal.getUserId()));
    }
}
