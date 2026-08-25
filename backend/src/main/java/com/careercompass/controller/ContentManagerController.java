package com.careercompass.controller;

import com.careercompass.dto.request.AddDraftSkillRequest;
import com.careercompass.dto.request.DeleteDraftSkillRequest;
import com.careercompass.dto.request.PublishLearningOutcomeRequest;
import com.careercompass.dto.request.ReplaceDraftSkillRequest;
import com.careercompass.dto.request.SelectStudyFieldRequest;
import com.careercompass.dto.request.UpdateDraftSkillRequest;
import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.dto.response.DraftSkillResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.dto.response.TaxonomySkillSearchResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.LearningOutcomeReviewService;
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
 *
 * <p>The learning-outcome endpoints cover the full proposal lifecycle: upload → extraction
 * (submit / poll / retry / cancel) → skill review (list / add / edit / replace / remove) →
 * publish. Every route is scoped to the authenticated manager's own rows; the service layer
 * enforces that again so a forged id cannot cross accounts.
 */
@RestController
@RequestMapping("/api/content-managers/me")
@RequiredArgsConstructor
public class ContentManagerController {

    private final LearningOutcomeService learningOutcomeService;
    private final LearningOutcomeReviewService reviewService;

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

    /**
     * FR-CM-04: upload a course learning-outcome PDF and start extraction. The qualified
     * course identity is deliberately supplied by the content manager rather than inferred
     * from a filename or from text extracted from the PDF.
     */
    @PostMapping(value = "/learning-outcomes", consumes = "multipart/form-data")
    public ResponseEntity<LearningOutcomeResponse> uploadLearningOutcome(
            @CurrentUser UserPrincipal principal,
            @RequestParam("courseCode") String courseCode,
            @RequestParam("catalogVersion") String catalogVersion,
            @RequestParam("courseName") String courseName,
            @RequestParam(value = "description", required = false) String description,
            @RequestParam("file") MultipartFile file) {
        LearningOutcomeResponse response = learningOutcomeService.uploadLearningOutcome(
                principal.getUserId(), courseCode, catalogVersion, courseName, description, file);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/learning-outcomes")
    public ResponseEntity<List<LearningOutcomeResponse>> listMyUploads(@CurrentUser UserPrincipal principal) {
        return ResponseEntity.ok(learningOutcomeService.listMyUploads(principal.getUserId()));
    }

    @GetMapping("/learning-outcomes/{outcomeId}")
    public ResponseEntity<LearningOutcomeResponse> getLearningOutcome(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(reviewService.getOutcome(principal.getUserId(), outcomeId));
    }

    /** Poll while an extraction or publication is running; persists observed transitions. */
    @GetMapping("/learning-outcomes/{outcomeId}/extraction")
    public ResponseEntity<LearningOutcomeResponse> getExtractionStatus(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(reviewService.getExtractionStatus(principal.getUserId(), outcomeId));
    }

    /** Re-run extraction for a failed, cancelled, or never-started upload. */
    @PostMapping("/learning-outcomes/{outcomeId}/extraction/retry")
    public ResponseEntity<LearningOutcomeResponse> retryExtraction(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(reviewService.retryExtraction(principal.getUserId(), outcomeId));
    }

    /** Stop a queued or running extraction; the stored PDF stays retryable. */
    @DeleteMapping("/learning-outcomes/{outcomeId}/extraction")
    public ResponseEntity<LearningOutcomeResponse> cancelExtraction(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(reviewService.cancelExtraction(principal.getUserId(), outcomeId));
    }

    @GetMapping("/learning-outcomes/{outcomeId}/skills")
    public ResponseEntity<List<DraftSkillResponse>> listDraftSkills(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(reviewService.listDraftSkills(principal.getUserId(), outcomeId));
    }

    /** Add a canonical taxonomy skill the extraction missed. */
    @PostMapping("/learning-outcomes/{outcomeId}/skills")
    public ResponseEntity<DraftSkillResponse> addDraftSkill(
            @CurrentUser UserPrincipal principal,
            @PathVariable Integer outcomeId,
            @Valid @RequestBody AddDraftSkillRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(reviewService.addDraftSkill(principal.getUserId(), outcomeId, request));
    }

    /** Edit one proposal's level, weight, note, or decision. */
    @PatchMapping("/learning-outcomes/{outcomeId}/skills/{draftSkillId}")
    public ResponseEntity<DraftSkillResponse> updateDraftSkill(
            @CurrentUser UserPrincipal principal,
            @PathVariable Integer outcomeId,
            @PathVariable Long draftSkillId,
            @Valid @RequestBody UpdateDraftSkillRequest request) {
        return ResponseEntity.ok(reviewService.updateDraftSkill(
                principal.getUserId(), outcomeId, draftSkillId, request));
    }

    /** Swap an AI suggestion (or unresolved term) for a reviewed canonical skill. */
    @PutMapping("/learning-outcomes/{outcomeId}/skills/{draftSkillId}/replacement")
    public ResponseEntity<DraftSkillResponse> replaceDraftSkill(
            @CurrentUser UserPrincipal principal,
            @PathVariable Integer outcomeId,
            @PathVariable Long draftSkillId,
            @Valid @RequestBody ReplaceDraftSkillRequest request) {
        return ResponseEntity.ok(reviewService.replaceDraftSkill(
                principal.getUserId(), outcomeId, draftSkillId, request));
    }

    /** Soft-delete a proposal; its review history is retained for audit. */
    @DeleteMapping("/learning-outcomes/{outcomeId}/skills/{draftSkillId}")
    public ResponseEntity<DraftSkillResponse> deleteDraftSkill(
            @CurrentUser UserPrincipal principal,
            @PathVariable Integer outcomeId,
            @PathVariable Long draftSkillId,
            @Valid @RequestBody DeleteDraftSkillRequest request) {
        return ResponseEntity.ok(reviewService.deleteDraftSkill(
                principal.getUserId(), outcomeId, draftSkillId, request));
    }

    /** Canonical taxonomy search backing manual additions and replacements. */
    @GetMapping("/skills/search")
    public ResponseEntity<TaxonomySkillSearchResponse> searchTaxonomySkills(
            @CurrentUser UserPrincipal principal,
            @RequestParam("q") String query,
            @RequestParam(value = "limit", required = false) Integer limit) {
        return ResponseEntity.ok(reviewService.searchTaxonomySkills(query, limit));
    }

    /** Approve the reviewed draft and publish it as the course's latest map version. */
    @PostMapping("/learning-outcomes/{outcomeId}/publish")
    public ResponseEntity<LearningOutcomeResponse> publishLearningOutcome(
            @CurrentUser UserPrincipal principal,
            @PathVariable Integer outcomeId,
            @Valid @RequestBody PublishLearningOutcomeRequest request) {
        return ResponseEntity.ok(
                reviewService.publishLearningOutcome(principal.getUserId(), outcomeId, request));
    }

    @DeleteMapping("/learning-outcomes/{outcomeId}/file")
    public ResponseEntity<LearningOutcomeResponse> deleteRawFile(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(learningOutcomeService.deleteRawFile(principal.getUserId(), outcomeId));
    }
}
