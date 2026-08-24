package com.careercompass.controller;

import com.careercompass.dto.request.SelectStudyFieldRequest;
import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.LearningOutcomeService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * Content Manager self-service endpoints (FR-CM-04/05). Restricted to ROLE_CONTENT_MANAGER
 * via SecurityConfig's `/api/content-managers/**` path rule. Same `/me` + `@CurrentUser`
 * pattern as every other actor controller.
 */
@RestController
@RequestMapping("/api/content-managers/me")
@RequiredArgsConstructor
public class ContentManagerController {

    private final LearningOutcomeService learningOutcomeService;

    /**
     * FR-CM-06: the signed-in Content Manager's own account.
     *
     * <p>Every other actor already had this ({@code JobSeekerController.getMyProfile},
     * {@code EmployerController.getMyProfile}, {@code ExpertController.getMyProfile}); the
     * Content Manager was the only one without it. The consequence was not cosmetic — the sole
     * endpoint returning a {@link ContentManagerResponse} that this role could reach was the
     * {@code PUT} below, so a client had to change the account to discover its current state.
     */
    @GetMapping
    public ResponseEntity<ContentManagerResponse> getMyProfile(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(learningOutcomeService.getMyProfile(principal.getUserId()));
    }

    /** FR-CM-05: select the study field taught. */
    @PutMapping("/study-field")
    public ResponseEntity<ContentManagerResponse> selectStudyField(
            @CurrentUser UserPrincipal principal, @Valid @RequestBody SelectStudyFieldRequest request) {
        return ResponseEntity.ok(
                learningOutcomeService.selectStudyField(principal.getUserId(), request.getStudyFieldId()));
    }

    /** FR-CM-04: upload a course learning-outcome PDF. */
    @PostMapping(value = "/learning-outcomes", consumes = "multipart/form-data")
    public ResponseEntity<LearningOutcomeResponse> uploadLearningOutcome(
            @CurrentUser UserPrincipal principal,
            @RequestParam("courseName") String courseName,
            @RequestParam(value = "description", required = false) String description,
            @RequestParam("file") MultipartFile file) {
        LearningOutcomeResponse response = learningOutcomeService.uploadLearningOutcome(
                principal.getUserId(), courseName, description, file);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/learning-outcomes")
    public ResponseEntity<List<LearningOutcomeResponse>> listMyUploads(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(learningOutcomeService.listMyUploads(principal.getUserId()));
    }

    @DeleteMapping("/learning-outcomes/{outcomeId}/file")
    public ResponseEntity<LearningOutcomeResponse> deleteRawFile(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(learningOutcomeService.deleteRawFile(principal.getUserId(), outcomeId));
    }
}
