package com.careercompass.service;

import com.careercompass.dto.request.AddDraftSkillRequest;
import com.careercompass.dto.request.DeleteDraftSkillRequest;
import com.careercompass.dto.request.PublishLearningOutcomeRequest;
import com.careercompass.dto.request.ReplaceDraftSkillRequest;
import com.careercompass.dto.request.UpdateDraftSkillRequest;
import com.careercompass.dto.response.DraftSkillResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.dto.response.TaxonomySkillResponse;
import com.careercompass.dto.response.TaxonomySkillSearchResponse;
import com.careercompass.entity.CourseSkillMapItem;
import com.careercompass.entity.CourseSkillMapState;
import com.careercompass.entity.CourseSkillMapVersion;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.LearningOutcome;
import com.careercompass.entity.LearningOutcomeExtractionStatus;
import com.careercompass.entity.LearningOutcomeSkillDraft;
import com.careercompass.entity.SkillDraftDecision;
import com.careercompass.exception.AiServiceException;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.StaleResourceException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.PublishCourseMapRequest;
import com.careercompass.integration.dto.SyllabusExtractionRequest;
import com.careercompass.integration.dto.SyllabusExtractionResponse;
import com.careercompass.integration.dto.SyllabusPreviewResponse;
import com.careercompass.integration.dto.TaxonomySkillSuggestion;
import com.careercompass.mapper.LearningOutcomeMapper;
import com.careercompass.mapper.LearningOutcomeSkillDraftMapper;
import com.careercompass.repository.CourseSkillMapItemRepository;
import com.careercompass.repository.CourseSkillMapVersionRepository;
import com.careercompass.repository.LearningOutcomeRepository;
import com.careercompass.repository.LearningOutcomeSkillDraftRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Business Layer for reviewing an AI syllabus-extraction proposal and publishing the approved
 * course-skill map (FR-CM-04/05 review half, FR-AI-08).
 *
 * <p>The governing rule is proposal-only: nothing the AI service returns is ever visible to
 * student analysis. Skills land in {@code learning_outcome_skill_drafts} for human review, and
 * only the content manager's approved subset is copied into an append-only
 * {@code course_skill_map_versions} snapshot that the AI service indexes.
 *
 * <p>Concurrency is handled at two levels, because two browsers on the same review are a
 * supported situation rather than an error: the aggregate-level {@code draft_revision}
 * compare-and-swap serialises review mutations, and each draft row's {@code row_version}
 * (JPA {@code @Version}) catches same-row edit conflicts. A lost race answers 409
 * {@code STALE_RESOURCE} and the browser reloads the current draft.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class LearningOutcomeReviewService {

    private static final Set<String> VALID_LEVELS = Set.of("beginner", "intermediate", "advanced");
    private static final Set<LearningOutcomeExtractionStatus> RUNNING_STATUSES =
            Set.of(LearningOutcomeExtractionStatus.QUEUED, LearningOutcomeExtractionStatus.EXTRACTING);
    private static final Set<SkillDraftDecision> ACTIVE_DECISIONS =
            Set.of(SkillDraftDecision.PENDING, SkillDraftDecision.ACCEPTED,
                    SkillDraftDecision.REPLACED, SkillDraftDecision.ADDED);

    private final LearningOutcomeRepository learningOutcomeRepository;
    private final LearningOutcomeSkillDraftRepository draftRepository;
    private final CourseSkillMapVersionRepository mapVersionRepository;
    private final CourseSkillMapItemRepository mapItemRepository;
    private final DataAnalysisClient dataAnalysisClient;
    private final FileStorageService fileStorage;
    private final LearningOutcomeMapper learningOutcomeMapper;
    private final LearningOutcomeSkillDraftMapper draftMapper;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transactionTemplate;

    // ── Reading ──────────────────────────────────────────────────────────

    @Transactional(readOnly = true)
    public LearningOutcomeResponse getOutcome(Integer contentManagerId, Integer outcomeId) {
        LearningOutcome outcome = ownedOutcome(outcomeId, contentManagerId);
        return toResponse(outcome);
    }

    @Transactional(readOnly = true)
    public List<DraftSkillResponse> listDraftSkills(Integer contentManagerId, Integer outcomeId) {
        ownedOutcome(outcomeId, contentManagerId);
        return draftRepository
                .findByOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerIdOrderByDraftSkillIdAsc(
                        outcomeId, contentManagerId)
                .stream()
                .map(draftMapper::toResponse)
                .toList();
    }

    /**
     * Read-only scan of an uploaded syllabus PDF used to pre-fill the upload form.
     * Runs no matching and writes nothing — the AI service parses identity fields
     * (course code, title, description) straight from the document.
     */
    public SyllabusPreviewResponse previewSyllabusPdf(String filename, String contentType, byte[] content) {
        return dataAnalysisClient.previewSyllabusPdf(filename, contentType, content);
    }

    /** Bounded canonical-taxonomy search backing manual additions and replacements. */
    public TaxonomySkillSearchResponse searchTaxonomySkills(String query, Integer limit) {        int bounded = limit == null ? 20 : Math.max(1, Math.min(50, limit));
        List<TaxonomySkillSuggestion> items =
                dataAnalysisClient.searchTaxonomySkills(query == null ? "" : query.trim(), bounded);
        return TaxonomySkillSearchResponse.builder()
                .total(items.size())
                .items(items.stream()
                        .map(item -> TaxonomySkillResponse.builder()
                                .skillId(item.getSkillId())
                                .label(item.getLabel())
                                .skillType(item.getSkillType())
                                .source(item.getSource())
                                .description(item.getDescription())
                                .taxonomyVersion(item.getTaxonomyVersion())
                                .build())
                        .toList())
                .build();
    }

    // ── Extraction lifecycle ─────────────────────────────────────────────

    /**
     * Polling resource for the review page. While the extraction runs it forwards to the AI
     * service and persists any terminal transition it observes, so a content manager who
     * closes the browser mid-extraction never loses the proposal.
     */
    @Transactional
    public LearningOutcomeResponse getExtractionStatus(Integer contentManagerId, Integer outcomeId) {
        LearningOutcome outcome = ownedOutcome(outcomeId, contentManagerId);
        if (RUNNING_STATUSES.contains(outcome.getExtractionStatus())
                && outcome.getAiExtractionId() != null) {
            applyExtractionUpdate(outcome, dataAnalysisClient.getSyllabusExtraction(outcome.getAiExtractionId()));
        }
        return toResponse(outcome);
    }

    /**
     * Re-runs extraction for a FAILED, CANCELLED, or never-started upload. Requires the raw
     * PDF to still be on disk — a deleted file cannot be re-analysed, and pretending otherwise
     * would turn one confusing error into two.
     */
    @Transactional
    public LearningOutcomeResponse retryExtraction(Integer contentManagerId, Integer outcomeId) {
        LearningOutcome outcome = ownedOutcome(outcomeId, contentManagerId);

        if (!RUNNING_STATUSES.contains(outcome.getExtractionStatus())
                && outcome.getExtractionStatus() != LearningOutcomeExtractionStatus.FAILED
                && outcome.getExtractionStatus() != LearningOutcomeExtractionStatus.CANCELLED
                && outcome.getExtractionStatus() != LearningOutcomeExtractionStatus.UPLOADED) {
            throw new PrerequisiteNotMetException(
                    "Extraction is " + outcome.getExtractionStatus() + "; only a failed, cancelled, "
                            + "or not-yet-started extraction can be retried.");
        }
        if (Boolean.TRUE.equals(outcome.getIsDeletedFromDisk())) {
            throw new PrerequisiteNotMetException(
                    "The uploaded PDF was removed from storage, so extraction cannot be retried. "
                            + "Upload the file again instead.");
        }

        byte[] content = fileBytes(outcome);

        draftRepository.deleteByOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(
                outcomeId, contentManagerId);

        outcome.setExtractionStatus(LearningOutcomeExtractionStatus.QUEUED);
        outcome.setExtractionError(null);
        outcome.setExtractionWarningsJson(null);
        outcome = learningOutcomeRepository.save(outcome);

        beginExtraction(outcome, content, outcome.getOriginalFilename(), "application/pdf", true);
        return toResponse(outcome);
    }

    /**
     * Stops a queued or running extraction. The stored PDF is untouched, so the upload stays
     * retryable. If the job already finished remotely, its result is applied rather than
     * thrown away — a finished proposal is worth more than an empty CANCELLED row.
     */
    @Transactional
    public LearningOutcomeResponse cancelExtraction(Integer contentManagerId, Integer outcomeId) {
        LearningOutcome outcome = ownedOutcome(outcomeId, contentManagerId);

        if (!RUNNING_STATUSES.contains(outcome.getExtractionStatus())) {
            throw new PrerequisiteNotMetException(
                    "Extraction is " + outcome.getExtractionStatus() + " and cannot be cancelled.");
        }

        if (outcome.getAiExtractionId() != null) {
            SyllabusExtractionResponse remote =
                    dataAnalysisClient.getSyllabusExtraction(outcome.getAiExtractionId());
            if (isTerminal(remote)) {
                applyExtractionUpdate(outcome, remote);
                return toResponse(outcome);
            }
            try {
                dataAnalysisClient.cancelSyllabusExtraction(outcome.getAiExtractionId());
            } catch (AiServiceException ex) {
                // The AI job store is in-memory; after a service restart the job no longer
                // exists. That is indistinguishable from "already stopped" for our purposes.
                if (ex.getStatus() != HttpStatus.NOT_FOUND) {
                    throw ex;
                }
                log.info("AI extraction {} already gone; cancelling locally", outcome.getAiExtractionId());
            }
        }

        outcome.setExtractionStatus(LearningOutcomeExtractionStatus.CANCELLED);
        outcome = learningOutcomeRepository.save(outcome);
        return toResponse(outcome);
    }

    /**
     * Submits the PDF to the AI service as a proposal ({@code storeResults=false}) and applies
     * whatever terminal state came back synchronously. Shared by first upload and retry.
     * A submission failure marks the row FAILED instead of failing the upload — the file is
     * safely stored and the content manager can retry, which matches the contract's rule that
     * extraction problems are job statuses, not HTTP statuses.
     */
    public void beginExtraction(LearningOutcome outcome, byte[] fileContent,
                                String originalFilename, String contentType, boolean force) {
        try {
            SyllabusExtractionResponse response = dataAnalysisClient.submitSyllabusExtraction(
                    SyllabusExtractionRequest.builder()
                            .fileContent(fileContent)
                            .originalFilename(originalFilename)
                            .contentType(contentType)
                            .useLlm(false)
                            .force(force)
                            .storeResults(false)
                            .build());
            if (response.getContentSha256() != null && !response.getContentSha256().isBlank()) {
                outcome.setContentSha256(response.getContentSha256());
            }
            outcome.setAiExtractionId(response.getExtractionId());
            outcome.setExtractionWarningsJson(toJson(response.getWarnings()));
            applyExtractionUpdate(outcome, response);
        } catch (RuntimeException ex) {
            log.warn("Syllabus extraction submission failed for outcome {}: {}",
                    outcome.getOutcomeId(), ex.getMessage());
            outcome.setExtractionStatus(LearningOutcomeExtractionStatus.FAILED);
            outcome.setExtractionError(humanMessage(ex));
        }
    }

    /**
     * Applies one AI extraction response to the aggregate. Terminal states persist the
     * proposal (or the failure); running states only advance the visible status.
     */
    private void applyExtractionUpdate(LearningOutcome outcome, SyllabusExtractionResponse response) {
        if (response == null || response.getStatus() == null) {
            return;
        }
        switch (response.getStatus().toLowerCase(Locale.ROOT)) {
            case "succeeded" -> {
                persistDrafts(outcome, response);
                outcome.setExtractionStatus(LearningOutcomeExtractionStatus.READY_FOR_REVIEW);
                outcome.setExtractionError(null);
            }
            case "failed" -> {
                outcome.setExtractionStatus(LearningOutcomeExtractionStatus.FAILED);
                outcome.setExtractionError(response.getError() != null && !response.getError().isBlank()
                        ? response.getError()
                        : "The AI service could not extract this syllabus.");
            }
            case "cancelled" ->
                    outcome.setExtractionStatus(LearningOutcomeExtractionStatus.CANCELLED);
            default -> {
                if (outcome.getExtractionStatus() != LearningOutcomeExtractionStatus.PUBLISHED) {
                    outcome.setExtractionStatus(LearningOutcomeExtractionStatus.EXTRACTING);
                }
            }
        }
    }

    private void persistDrafts(LearningOutcome outcome, SyllabusExtractionResponse response) {
        SyllabusExtractionResponse.Result result = response.getResult();
        if (result == null || result.getSkills() == null || result.getSkills().isEmpty()) {
            outcome.setExtractionError(
                    "Extraction succeeded but produced no skills; add them manually before publishing.");
            return;
        }
        if (result.getTaxonomyVersion() != null && !result.getTaxonomyVersion().isBlank()) {
            outcome.setTaxonomyVersion(result.getTaxonomyVersion());
        }

        // A retry may legally land on a completed proposal while stale drafts linger.
        draftRepository.deleteByOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(
                outcome.getOutcomeId(), outcome.getUploadedByContentManager().getContentManagerId());

        Set<String> seenTerms = new HashSet<>();
        List<LearningOutcomeSkillDraft> drafts = new ArrayList<>();
        for (SyllabusExtractionResponse.ExtractedSkill skill : result.getSkills()) {
            String term = skill.getTerm() == null ? "" : skill.getTerm().trim();
            if (term.isEmpty()) {
                continue;
            }
            // The (outcome_id, term) unique key is the proposal's identity; a duplicate
            // extraction term is redundant evidence, not a new row.
            if (!seenTerms.add(term.toLowerCase(Locale.ROOT))) {
                continue;
            }
            drafts.add(buildDraft(outcome, term, skill));
        }
        draftRepository.saveAll(drafts);
    }

    private LearningOutcomeSkillDraft buildDraft(LearningOutcome outcome, String term,
                                                 SyllabusExtractionResponse.ExtractedSkill skill) {
        SyllabusExtractionResponse.CanonicalSkill canonical = skill.getCanonical();
        SyllabusExtractionResponse.Match match = skill.getMatch();

        String canonicalId = firstNonBlank(
                canonical == null ? null : canonical.getId(),
                match == null ? null : match.getCanonicalId());
        String canonicalLabel = firstNonBlank(
                canonical == null ? null : canonical.getLabel(),
                match == null ? null : match.getCanonicalLabel());

        return LearningOutcomeSkillDraft.builder()
                .outcome(outcome)
                .term(term)
                .canonicalSkillId(blankToNull(canonicalId))
                .canonicalLabel(blankToNull(canonicalLabel))
                .originalCanonicalSkillId(blankToNull(canonicalId))
                .originalCanonicalLabel(blankToNull(canonicalLabel))
                .level(normalizeLevel(skill.getLevel()))
                .weight(clamp01(skill.getWeight()))
                .evidenceCount(skill.getEvidenceCount() == null ? 0 : Math.max(0, skill.getEvidenceCount()))
                .evidenceJson(toJson(skill.getEvidence()))
                .sourcesJson(toJson(skill.getSources()))
                .candidatesJson(toJson(match == null ? null : match.getCandidates()))
                .matchMethod(match == null ? null : match.getMatchMethod())
                .matchScore(match == null ? null : clamp01(match.getMatchScore()))
                .matchReason(match == null ? null : match.getReason())
                .aiReviewStatus(firstNonBlank(
                        match == null ? null : match.getReviewStatus(), "no_match"))
                .decision(SkillDraftDecision.PENDING)
                .build();
    }

    // ── Draft mutations ──────────────────────────────────────────────────

    @Transactional
    public DraftSkillResponse addDraftSkill(Integer contentManagerId, Integer outcomeId,
                                            AddDraftSkillRequest request) {
        LearningOutcome outcome = ownedEditableOutcome(outcomeId, contentManagerId,
                request.getExpectedDraftRevision());

        String canonicalId = request.getSkillId().trim();
        String label = firstNonBlank(request.getSkillLabel(), resolveTaxonomyLabel(canonicalId), canonicalId);
        String term = firstNonBlank(request.getTerm(), label, canonicalId);

        if (draftRepository.findByOutcome_OutcomeIdAndTermIgnoreCase(outcomeId, term).isPresent()) {
            throw new DuplicateResourceException(
                    "A skill for the term \"" + term + "\" is already in this draft.");
        }
        if (draftRepository.existsByOutcome_OutcomeIdAndCanonicalSkillIdAndDecisionIn(
                outcomeId, canonicalId, ACTIVE_DECISIONS)) {
            throw new DuplicateResourceException(
                    "The canonical skill " + canonicalId + " is already in this draft.");
        }

        LearningOutcomeSkillDraft draft = LearningOutcomeSkillDraft.builder()
                .outcome(outcome)
                .term(term)
                .canonicalSkillId(canonicalId)
                .canonicalLabel(label)
                .level(normalizeLevel(request.getLevel()))
                .weight(clamp01(request.getWeight()))
                .evidenceCount(0)
                .aiReviewStatus("manual")
                .matchMethod("manual")
                .decision(SkillDraftDecision.ADDED)
                .note(blankToNull(request.getNote()))
                .build();
        return draftMapper.toResponse(draftRepository.save(draft));
    }

    @Transactional
    public DraftSkillResponse updateDraftSkill(Integer contentManagerId, Integer outcomeId,
                                               Long draftSkillId, UpdateDraftSkillRequest request) {
        LearningOutcomeSkillDraft draft = ownedEditableDraft(contentManagerId, outcomeId, draftSkillId, request.getExpectedDraftRevision(), request.getExpectedRowVersion());

        if (request.getLevel() != null) {
            draft.setLevel(normalizeLevel(request.getLevel()));
        }
        if (request.getWeight() != null) {
            draft.setWeight(clamp01(request.getWeight()));
        }
        if (request.getNote() != null) {
            draft.setNote(blankToNull(request.getNote()));
        }
        if (request.getDecision() != null) {
            applyExplicitDecision(draft, request.getDecision());
        }
        // Flush so the response carries the post-update @Version: the browser needs the new
        // row_version for its next mutation on this row, not the pre-update one.
        return draftMapper.toResponse(draftRepository.saveAndFlush(draft));
    }

    @Transactional
    public DraftSkillResponse replaceDraftSkill(Integer contentManagerId, Integer outcomeId,
                                                Long draftSkillId, ReplaceDraftSkillRequest request) {
        LearningOutcomeSkillDraft draft = ownedEditableDraft(contentManagerId, outcomeId, draftSkillId, request.getExpectedDraftRevision(), request.getExpectedRowVersion());

        String replacementId = request.getReplacementSkillId().trim();
        if (!replacementId.equals(draft.getCanonicalSkillId())
                && draftRepository.existsByOutcome_OutcomeIdAndCanonicalSkillIdAndDecisionIn(
                        outcomeId, replacementId, ACTIVE_DECISIONS)) {
            throw new DuplicateResourceException(
                    "The canonical skill " + replacementId + " is already used by another skill in this draft.");
        }

        if (draft.getOriginalCanonicalSkillId() == null) {
            draft.setOriginalCanonicalSkillId(draft.getCanonicalSkillId());
            draft.setOriginalCanonicalLabel(draft.getCanonicalLabel());
        }
        draft.setCanonicalSkillId(replacementId);
        draft.setCanonicalLabel(firstNonBlank(
                resolveTaxonomyLabel(replacementId), replacementId));
        draft.setDecision(SkillDraftDecision.REPLACED);
        if (request.getNote() != null) {
            draft.setNote(blankToNull(request.getNote()));
        }
        return draftMapper.toResponse(draftRepository.saveAndFlush(draft));
    }

    @Transactional
    public DraftSkillResponse deleteDraftSkill(Integer contentManagerId, Integer outcomeId,
                                               Long draftSkillId, DeleteDraftSkillRequest request) {
        LearningOutcomeSkillDraft draft = ownedEditableDraft(contentManagerId, outcomeId, draftSkillId,
                request.getExpectedDraftRevision(), request.getExpectedRowVersion());
        draft.setDecision(SkillDraftDecision.REMOVED);
        return draftMapper.toResponse(draftRepository.saveAndFlush(draft));
    }

    /** ACCEPTED requires a canonical identity; system-managed decisions are never client-set. */
    private void applyExplicitDecision(LearningOutcomeSkillDraft draft, SkillDraftDecision decision) {
        switch (decision) {
            case PENDING, REMOVED -> draft.setDecision(decision);
            case ACCEPTED -> {
                if (draft.getCanonicalSkillId() == null) {
                    throw new PrerequisiteNotMetException(
                            "Resolve the canonical skill before accepting this term.");
                }
                draft.setDecision(SkillDraftDecision.ACCEPTED);
            }
            default -> throw new IllegalArgumentException(
                    "Decision " + decision + " is managed by the replace and add operations.");
        }
    }

    // ── Publication ──────────────────────────────────────────────────────

    /**
     * Copies the approved subset of the draft into a new append-only map version and hands it
     * to the AI service as one idempotent replacement.
     *
     * <p>Transaction boundaries matter here: the {@code PUBLISHING} snapshot must be committed
     * before the remote call, and a remote failure must leave a durable FAILED record while
     * still answering 502. Both are impossible inside the single declarative transaction that
     * would otherwise wrap this method, so the three steps use explicit transactions.
     */
    public LearningOutcomeResponse publishLearningOutcome(Integer contentManagerId, Integer outcomeId,
                                                          PublishLearningOutcomeRequest request) {
        PublicationSnapshot snapshot = transactionTemplate.execute(tx ->
                preparePublication(contentManagerId, outcomeId, request.getExpectedDraftRevision()));

        try {
            dataAnalysisClient.publishCourseMap(toPublishRequest(snapshot));
        } catch (RuntimeException ex) {
            transactionTemplate.executeWithoutResult(tx ->
                    markPublicationFailed(snapshot, humanMessage(ex)));
            if (ex instanceof AiServiceException ai && ai.getStatus() == HttpStatus.CONFLICT) {
                throw new DuplicateResourceException("This course map version is already published or conflicts with another map.");
            }
            throw ex instanceof AiServiceException ai ? ai
                    : new AiServiceException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_RESPONSE_INVALID",
                            humanMessage(ex), ex);
        }

        transactionTemplate.executeWithoutResult(tx -> completePublication(snapshot));
        return transactionTemplate.execute(tx ->
                toResponse(learningOutcomeRepository.findById(outcomeId).orElse(snapshot.outcome())));
    }

    private PublicationSnapshot preparePublication(Integer contentManagerId, Integer outcomeId,
                                                   Long expectedDraftRevision) {
        LearningOutcome outcome = ownedEditableOutcome(outcomeId, contentManagerId, expectedDraftRevision);

        List<LearningOutcomeSkillDraft> drafts = draftRepository
                .findByOutcome_OutcomeIdOrderByDraftSkillIdAsc(outcomeId);
        List<LearningOutcomeSkillDraft> active = drafts.stream()
                .filter(draft -> draft.getDecision() != SkillDraftDecision.REMOVED)
                .toList();

        if (active.isEmpty()) {
            throw new PrerequisiteNotMetException(
                    "Keep at least one skill in the course map before publishing.");
        }
        long pending = active.stream()
                .filter(draft -> draft.getDecision() == SkillDraftDecision.PENDING).count();
        if (pending > 0) {
            throw new PrerequisiteNotMetException(
                    pending + " skill(s) are still pending review. Accept, replace, or remove them first.");
        }
        List<LearningOutcomeSkillDraft> unresolved = active.stream()
                .filter(draft -> draft.getCanonicalSkillId() == null).toList();
        if (!unresolved.isEmpty()) {
            throw new PrerequisiteNotMetException(
                    unresolved.size() + " skill(s) have no canonical skill. Replace them with taxonomy entries first.");
        }

        Set<String> seen = new HashSet<>();
        for (LearningOutcomeSkillDraft draft : active) {
            if (!seen.add(draft.getCanonicalSkillId())) {
                throw new DuplicateResourceException(
                        "The canonical skill " + draft.getCanonicalSkillId()
                                + " appears more than once in the approved draft.");
            }
        }
        String taxonomyVersion = outcome.getTaxonomyVersion();
        if (taxonomyVersion == null || taxonomyVersion.isBlank()) {
            throw new PrerequisiteNotMetException(
                    "The extraction did not record a taxonomy version, so the course map cannot be published safely.");
        }

        long mapVersion = mapVersionRepository.findLatestMapVersion(
                outcome.getInstitutionCode(), outcome.getCatalogVersion(), outcome.getCourseCode()) + 1;

        List<CourseSkillMapItem> items = active.stream()
                .map(draft -> buildMapItem(outcome, draft))
                .toList();
        String checksum = publicationChecksum(items);

        ContentManager approver = outcome.getUploadedByContentManager();
        CourseSkillMapVersion map = mapVersionRepository.save(CourseSkillMapVersion.builder()
                .institutionCode(outcome.getInstitutionCode())
                .catalogVersion(outcome.getCatalogVersion())
                .courseCode(outcome.getCourseCode())
                .mapVersion(mapVersion)
                .state(CourseSkillMapState.PUBLISHING)
                .taxonomyVersion(taxonomyVersion)
                .approvedByContentManager(approver)
                .sourceOutcome(outcome)
                .checksum(checksum)
                .build());
        mapItemRepository.saveAll(items.stream()
                .map(item -> withMap(item, map))
                .toList());

        return new PublicationSnapshot(outcome, map.getMapId(), mapVersion, taxonomyVersion, items);
    }

    private void completePublication(PublicationSnapshot snapshot) {
        CourseSkillMapVersion map = mapVersionRepository.findById(snapshot.mapId()).orElseThrow();
        map.setState(CourseSkillMapState.PUBLISHED);
        map.setPublishedAt(LocalDateTime.now());
        mapVersionRepository.save(map);

        LearningOutcome outcome = learningOutcomeRepository.findById(snapshot.outcome().getOutcomeId())
                .orElse(snapshot.outcome());
        outcome.setExtractionStatus(LearningOutcomeExtractionStatus.PUBLISHED);
        outcome.setCourseMapVersion(snapshot.mapVersion());
        outcome.setPublishedAt(map.getPublishedAt());
        learningOutcomeRepository.save(outcome);
    }

    private void markPublicationFailed(PublicationSnapshot snapshot, String message) {
        CourseSkillMapVersion map = mapVersionRepository.findById(snapshot.mapId()).orElse(null);
        if (map == null || map.getState() != CourseSkillMapState.PUBLISHING) {
            return;
        }
        map.setState(CourseSkillMapState.FAILED);
        map.setError(message);
        map.setFailedAt(LocalDateTime.now());
        mapVersionRepository.save(map);
        // The outcome deliberately stays READY_FOR_REVIEW: the review is intact and the
        // content manager can fix the cause and publish again.
    }

    private PublishCourseMapRequest toPublishRequest(PublicationSnapshot snapshot) {
        LearningOutcome outcome = snapshot.outcome();
        return PublishCourseMapRequest.builder()
                .courseMapVersion(String.format("%s-v%d", outcome.getOutcomeId(), snapshot.mapVersion()))
                .institutionCode(outcome.getInstitutionCode())
                .catalogVersion(outcome.getCatalogVersion())
                .courseCode(outcome.getCourseCode())
                .sourceOutcomeId(String.valueOf(outcome.getOutcomeId()))
                .taxonomyVersion(snapshot.taxonomyVersion())
                .skills(snapshot.items().stream()
                        .map(item -> PublishCourseMapRequest.ApprovedSkill.builder()
                                .skillId(item.getCanonicalSkillId())
                                .skillLabel(item.getCanonicalLabel())
                                .term(item.getTerm())
                                .level(item.getLevel())
                                .weight(item.getWeight())
                                .evidenceCount(item.getEvidenceCount())
                                .sources(fromJsonStringList(item.getSourcesJson()))
                                .evidence(fromJsonEvidenceList(item.getEvidenceJson()))
                                .build())
                        .toList())
                .build();
    }

    private CourseSkillMapItem buildMapItem(LearningOutcome outcome, LearningOutcomeSkillDraft draft) {
        return CourseSkillMapItem.builder()
                .sourceDraftSkill(draft)
                .term(draft.getTerm())
                .canonicalSkillId(draft.getCanonicalSkillId())
                .canonicalLabel(draft.getCanonicalLabel())
                .level(draft.getLevel())
                .weight(draft.getWeight())
                .evidenceCount(draft.getEvidenceCount())
                .sourcesJson(draft.getSourcesJson())
                .evidenceJson(draft.getEvidenceJson())
                .decisionNote(draft.getNote())
                .build();
    }

    /** Deterministic SHA-256 over the approved items — the audit identity of this publication. */
    private String publicationChecksum(List<CourseSkillMapItem> items) {
        String canonical = items.stream()
                .sorted(Comparator.comparing(CourseSkillMapItem::getCanonicalSkillId))
                .map(item -> String.join("|",
                        item.getCanonicalSkillId(),
                        item.getCanonicalLabel(),
                        item.getTerm(),
                        item.getLevel(),
                        item.getWeight().toPlainString(),
                        String.valueOf(item.getEvidenceCount())))
                .reduce((a, b) -> a + "\n" + b)
                .orElse("");
        return sha256Hex(canonical.getBytes(StandardCharsets.UTF_8));
    }

    // ── Shared helpers ───────────────────────────────────────────────────

    /**
     * Loads the outcome scoped to its owner and asserts it is open for review edits, spending
     * the aggregate CAS first: a stale {@code expectedDraftRevision} answers 409 before any
     * row is touched.
     */
    private LearningOutcome ownedEditableOutcome(Integer outcomeId, Integer contentManagerId,
                                                 Long expectedDraftRevision) {
        LearningOutcome outcome = ownedOutcome(outcomeId, contentManagerId);
        if (outcome.getExtractionStatus() != LearningOutcomeExtractionStatus.READY_FOR_REVIEW) {
            throw new PrerequisiteNotMetException(
                    "This review is " + outcome.getExtractionStatus()
                            + " and can no longer be edited. Upload a new catalog version to propose changes.");
        }
        spendDraftRevision(outcomeId, contentManagerId, expectedDraftRevision);
        return outcome;
    }

    private LearningOutcomeSkillDraft ownedEditableDraft(Integer contentManagerId, Integer outcomeId,
                                                         Long draftSkillId, Long expectedDraftRevision,
                                                         Long expectedRowVersion) {
        LearningOutcome outcome = ownedEditableOutcome(outcomeId, contentManagerId, expectedDraftRevision);
        LearningOutcomeSkillDraft draft = draftRepository
                .findByDraftSkillIdAndOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(
                        draftSkillId, outcomeId, contentManagerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Draft skill with id " + draftSkillId + " not found in this review."));
        // The CAS above cleared the persistence context, so row_version is fresh here.
        if (!draft.getRowVersion().equals(expectedRowVersion)) {
            throw new StaleResourceException(
                    "This skill was changed by someone else while you were editing. Reload the draft and retry.");
        }
        return draft;
    }

    private LearningOutcome ownedOutcome(Integer outcomeId, Integer contentManagerId) {
        return learningOutcomeRepository
                .findByOutcomeIdAndUploadedByContentManager_ContentManagerId(outcomeId, contentManagerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Learning outcome with id " + outcomeId + " not found."));
    }

    private void spendDraftRevision(Integer outcomeId, Integer contentManagerId, Long expected) {
        if (expected == null) {
            throw new IllegalArgumentException("An expected draft revision is required.");
        }
        if (learningOutcomeRepository.advanceDraftRevision(outcomeId, contentManagerId, expected) == 0) {
            throw new StaleResourceException(
                    "This review changed while you were working. Reload the latest draft and try again.");
        }
    }

    /** Response projection including draft counts; shared with the upload flow. */
    @Transactional(readOnly = true)
    public LearningOutcomeResponse toResponse(LearningOutcome outcome) {
        long total = draftRepository.countByOutcome_OutcomeId(outcome.getOutcomeId());
        long pending = draftRepository.countByOutcome_OutcomeIdAndDecision(
                outcome.getOutcomeId(), SkillDraftDecision.PENDING);
        return learningOutcomeMapper.toResponse(outcome, total, pending);
    }

    private String resolveTaxonomyLabel(String skillId) {
        return dataAnalysisClient.searchTaxonomySkills(skillId, 10).stream()
                .filter(item -> skillId.equals(item.getSkillId()))
                .map(TaxonomySkillSuggestion::getLabel)
                .findFirst()
                .orElse(null);
    }

    private byte[] fileBytes(LearningOutcome outcome) {
        byte[] content = fileStorageBytes(outcome);
        if (content == null || content.length == 0) {
            throw new PrerequisiteNotMetException(
                    "The uploaded PDF is no longer on disk, so extraction cannot run. Upload the file again.");
        }
        return content;
    }

    private byte[] fileStorageBytes(LearningOutcome outcome) {
        return fileStorage.readIfExists(outcome.getFilePath());
    }

    private static boolean isTerminal(SyllabusExtractionResponse response) {
        if (response == null || response.getStatus() == null) {
            return false;
        }
        String status = response.getStatus().toLowerCase(Locale.ROOT);
        return status.equals("succeeded") || status.equals("failed") || status.equals("cancelled");
    }

    private static String normalizeLevel(String level) {
        if (level == null) {
            return "intermediate";
        }
        String lowered = level.trim().toLowerCase(Locale.ROOT);
        return VALID_LEVELS.contains(lowered) ? lowered : "intermediate";
    }

    private static BigDecimal clamp01(BigDecimal value) {
        if (value == null) {
            return BigDecimal.ZERO;
        }
        return switch (value.compareTo(BigDecimal.ZERO)) {
            case -1 -> BigDecimal.ZERO;
            default -> value.compareTo(BigDecimal.ONE) > 0 ? BigDecimal.ONE : value;
        };
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private String toJson(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            log.warn("Could not serialise extraction audit payload", ex);
            return null;
        }
    }

    private List<String> fromJsonStringList(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, new com.fasterxml.jackson.core.type.TypeReference<>() { });
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private List<java.util.Map<String, Object>> fromJsonEvidenceList(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, new com.fasterxml.jackson.core.type.TypeReference<>() { });
        } catch (JsonProcessingException ex) {
            return List.of();
        }
    }

    private CourseSkillMapItem withMap(CourseSkillMapItem item, CourseSkillMapVersion map) {
        item.setMapVersion(map);
        return item;
    }

    private static String humanMessage(RuntimeException ex) {
        String message = ex.getMessage();
        return message == null || message.isBlank()
                ? "The AI service could not complete this operation."
                : message;
    }

    static String sha256Hex(byte[] content) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(content));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable in this JVM.", ex);
        }
    }

    /**
     * Immutable hand-off between the publication's three transactional steps. Everything it
     * holds was committed by {@link #preparePublication}; the later steps re-read by ids.
     */
    private record PublicationSnapshot(
            LearningOutcome outcome,
            Long mapId,
            Long mapVersion,
            String taxonomyVersion,
            List<CourseSkillMapItem> items) {
    }
}
