package com.careercompass.controller;

import com.careercompass.dto.request.AddDraftSkillRequest;
import com.careercompass.dto.request.DeleteDraftSkillRequest;
import com.careercompass.dto.request.PublishLearningOutcomeRequest;
import com.careercompass.dto.request.ReplaceDraftSkillRequest;
import com.careercompass.dto.request.SelectStudyFieldRequest;
import com.careercompass.dto.request.UpdateDraftSkillRequest;
import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.dto.response.DraftSkillResponse;
import com.careercompass.dto.response.LearningOutcomePreviewResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.dto.response.TaxonomySkillSearchResponse;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.LearningOutcomeReviewService;
import com.careercompass.service.LearningOutcomeService;
import io.swagger.v3.oas.annotations.Parameter;
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
            // The @Parameter annotations are what put these fields in the generated OpenAPI
            // document. Without them springdoc describes a multipart body containing only
            // `file`, and a client written from the contract gets a 400 for the three required
            // text fields the spec never mentioned.
            @Parameter(description = "Course code, e.g. 0413403", required = true)
            @RequestParam("courseCode") String courseCode,
            @Parameter(description = "Catalog version, e.g. 2026-2027 or v3", required = true)
            @RequestParam("catalogVersion") String catalogVersion,
            @Parameter(description = "Human-readable course name", required = true)
            @RequestParam("courseName") String courseName,
            @Parameter(description = "Optional course description")
            @RequestParam(value = "description", required = false) String description,
            @Parameter(description = "The course PDF (text-based, max 10 MB)", required = true)
            @RequestParam("file") MultipartFile file) {
        LearningOutcomeResponse response = learningOutcomeService.uploadLearningOutcome(
                principal.getUserId(), courseCode, catalogVersion, courseName, description, file);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    /** FR-CM-04 aid: read-only scan that pre-fills the upload form from the PDF. */
    @PostMapping(value = "/learning-outcomes/preview", consumes = "multipart/form-data")
    public ResponseEntity<LearningOutcomePreviewResponse> previewLearningOutcomePdf(
            @CurrentUser UserPrincipal principal,
            @RequestParam("file") MultipartFile file) {
        return ResponseEntity.ok(learningOutcomeService.previewPdf(principal.getUserId(), file));
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

    /**
     * FR-CM-04: discard an upload entirely — the row, its draft skills and the PDF.
     *
     * <p>Not the same as {@code DELETE .../file}, which removes only the PDF and keeps everything
     * extracted from it. Refused once the outcome has been published to a course map.
     */
    @DeleteMapping("/learning-outcomes/{outcomeId}")
    public ResponseEntity<Void> deleteLearningOutcome(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        learningOutcomeService.deleteOutcome(principal.getUserId(), outcomeId);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/learning-outcomes/{outcomeId}/file")
    public ResponseEntity<LearningOutcomeResponse> deleteRawFile(
            @CurrentUser UserPrincipal principal, @PathVariable Integer outcomeId) {
        return ResponseEntity.ok(learningOutcomeService.deleteRawFile(principal.getUserId(), outcomeId));
    }
}
