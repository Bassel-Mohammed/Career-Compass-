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
