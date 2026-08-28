package com.careercompass.service;

import com.careercompass.dto.request.AddDraftSkillRequest;
import com.careercompass.dto.request.PublishLearningOutcomeRequest;
import com.careercompass.dto.request.UpdateDraftSkillRequest;
import com.careercompass.dto.response.DraftSkillResponse;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.LearningOutcome;
import com.careercompass.entity.LearningOutcomeExtractionStatus;
import com.careercompass.entity.LearningOutcomeSkillDraft;
import com.careercompass.entity.SkillDraftDecision;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.StaleResourceException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.mapper.LearningOutcomeMapper;
import com.careercompass.mapper.LearningOutcomeSkillDraftMapper;
import com.careercompass.repository.CourseSkillMapItemRepository;
import com.careercompass.repository.CourseSkillMapVersionRepository;
import com.careercompass.repository.LearningOutcomeRepository;
import com.careercompass.repository.LearningOutcomeSkillDraftRepository;
import com.careercompass.entity.CourseSkillMapVersion;
import com.careercompass.exception.AiServiceException;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.integration.dto.PublishCourseMapRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Optional;
import java.util.function.Consumer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for the review workflow's concurrency and publication guardrails. The happy
 * extraction → accept → publish path is covered end-to-end by CareerCompassSystemTest; these
 * tests pin the rules that protect two-browser reviews and published maps from silent damage.
 */
@ExtendWith(MockitoExtension.class)
class LearningOutcomeReviewServiceTest {

    @Mock private LearningOutcomeRepository learningOutcomeRepository;
    @Mock private LearningOutcomeSkillDraftRepository draftRepository;
    @Mock private CourseSkillMapVersionRepository mapVersionRepository;
    @Mock private CourseSkillMapItemRepository mapItemRepository;
    @Mock private DataAnalysisClient dataAnalysisClient;
    @Mock private FileStorageService fileStorage;
    @Mock private LearningOutcomeMapper learningOutcomeMapper;
    @Mock private LearningOutcomeSkillDraftMapper draftMapper;
    @Mock private ObjectMapper objectMapper;
    @Mock private TransactionTemplate transactionTemplate;

    @InjectMocks
    private LearningOutcomeReviewService reviewService;

    private ContentManager owner;
    private LearningOutcome outcome;

    @BeforeEach
    void setUp() {
        owner = ContentManager.builder().contentManagerId(1).build();
        outcome = LearningOutcome.builder()
                .outcomeId(10)
                .institutionCode("uni:10")
                .catalogVersion("2025-2026")
                .courseCode("CS201")
                .taxonomyVersion("taxonomy-2026.08")
                .extractionStatus(LearningOutcomeExtractionStatus.READY_FOR_REVIEW)
                .draftRevision(3L)
                .uploadedByContentManager(owner)
                .build();
        lenient().when(learningOutcomeRepository
                        .findByOutcomeIdAndUploadedByContentManager_ContentManagerId(10, 1))
                .thenReturn(Optional.of(outcome));
        // Run transactional callbacks inline for unit testing.
        lenient().when(transactionTemplate.execute(any()))
                .thenAnswer(inv -> ((TransactionCallback<?>) inv.getArgument(0)).doInTransaction(null));
        lenient().doAnswer(inv -> {
                    ((Consumer<TransactionStatus>) inv.getArgument(0)).accept(null);
                    return null;
                })
                .when(transactionTemplate).executeWithoutResult(any());
    }

    // Purpose: a mutation carrying an out-of-date draft revision is rejected before any row
    // is touched — two browsers can never silently overwrite each other's review.
    @Test
    void updateDraftSkill_rejectsStaleDraftRevision() {
        when(learningOutcomeRepository.advanceDraftRevision(10, 1, 2L)).thenReturn(0);

        UpdateDraftSkillRequest request = new UpdateDraftSkillRequest();
        request.setExpectedRowVersion(0L);
        request.setExpectedDraftRevision(2L);

        assertThatThrownBy(() -> reviewService.updateDraftSkill(1, 10, 5L, request))
                .isInstanceOf(StaleResourceException.class);

        verify(draftRepository, never()).save(any());
    }

    // Purpose: adding the same canonical skill twice would corrupt the published map's
    // unique identity, so the second add is a 409, not a silent duplicate.
    @Test
    void addDraftSkill_rejectsDuplicateCanonicalSkill() {
        when(learningOutcomeRepository.advanceDraftRevision(10, 1, 3L)).thenReturn(1);
        when(draftRepository.existsByOutcome_OutcomeIdAndCanonicalSkillIdAndDecisionIn(
                10, "skill:oop", LearningOutcomeReviewServiceTest.activeDecisions()))
                .thenReturn(true);

        AddDraftSkillRequest request = new AddDraftSkillRequest();
        request.setSkillId("skill:oop");
        request.setSkillLabel("Object-oriented programming");
        request.setLevel("beginner");
        request.setWeight(java.math.BigDecimal.valueOf(0.5));
        request.setExpectedDraftRevision(3L);

        assertThatThrownBy(() -> reviewService.addDraftSkill(1, 10, request))
                .isInstanceOf(DuplicateResourceException.class);

        verify(draftRepository, never()).save(any());
    }

    // Purpose: a review with unresolved terms cannot be published — the AI proposal must be
    // fully adjudicated before students can see any of it.
    @Test
    void publishLearningOutcome_rejectsUnresolvedDraft() {
        when(learningOutcomeRepository.advanceDraftRevision(10, 1, 3L)).thenReturn(1);
        when(draftRepository.findByOutcome_OutcomeIdOrderByDraftSkillIdAsc(10))
                .thenReturn(List.of(draft(1L, SkillDraftDecision.ACCEPTED, "skill:oop"),
                        draft(2L, SkillDraftDecision.PENDING, null)));

        PublishLearningOutcomeRequest request = new PublishLearningOutcomeRequest();
        request.setExpectedDraftRevision(3L);

        assertThatThrownBy(() -> reviewService.publishLearningOutcome(1, 10, request))
                .isInstanceOf(PrerequisiteNotMetException.class);

        verify(mapVersionRepository, never()).save(any());
        verify(dataAnalysisClient, never()).publishCourseMap(any());
    }

    // Purpose: an entirely empty draft cannot become a course map.
    @Test
    void publishLearningOutcome_rejectsEmptyDraft() {
        when(learningOutcomeRepository.advanceDraftRevision(10, 1, 3L)).thenReturn(1);
        when(draftRepository.findByOutcome_OutcomeIdOrderByDraftSkillIdAsc(10))
                .thenReturn(List.of());

        PublishLearningOutcomeRequest request = new PublishLearningOutcomeRequest();
        request.setExpectedDraftRevision(3L);

        assertThatThrownBy(() -> reviewService.publishLearningOutcome(1, 10, request))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }

    // Purpose: a review that is not open for edits (e.g. already PUBLISHED) rejects
    // mutations with the state named, rather than corrupting a map students already see.
    @Test
    void mutations_rejectOutcomeNotReadyForReview() {
        outcome.setExtractionStatus(LearningOutcomeExtractionStatus.PUBLISHED);

        UpdateDraftSkillRequest request = new UpdateDraftSkillRequest();
        request.setExpectedRowVersion(0L);
        request.setExpectedDraftRevision(3L);

        assertThatThrownBy(() -> reviewService.updateDraftSkill(1, 10, 5L, request))
                .isInstanceOf(PrerequisiteNotMetException.class)
                .hasMessageContaining("PUBLISHED");
    }

    // Purpose: accepting a term that has no canonical identity is blocked — the reviewer
    // must replace it with a taxonomy entry first.
    @Test
    void updateDraftSkill_rejectsAcceptingUnresolvedTerm() {
        when(learningOutcomeRepository.advanceDraftRevision(10, 1, 3L)).thenReturn(1);
        LearningOutcomeSkillDraft unresolved = draft(5L, SkillDraftDecision.PENDING, null);
        when(draftRepository.findByDraftSkillIdAndOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(
                5L, 10, 1)).thenReturn(Optional.of(unresolved));

        UpdateDraftSkillRequest request = new UpdateDraftSkillRequest();
        request.setDecision(SkillDraftDecision.ACCEPTED);
        request.setExpectedRowVersion(0L);
        request.setExpectedDraftRevision(3L);

        assertThatThrownBy(() -> reviewService.updateDraftSkill(1, 10, 5L, request))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }

    private static java.util.Collection<SkillDraftDecision> activeDecisions() {
        // Matches the service's active-decision set by value (Set.of equality).
        return java.util.Set.of(SkillDraftDecision.PENDING, SkillDraftDecision.ACCEPTED,
                SkillDraftDecision.REPLACED, SkillDraftDecision.ADDED);
    }

    @Test
    void publishLearningOutcome_usesGloballyQualifiedVersionAndMaps409Conflict() {
        // Arrange
        LearningOutcomeSkillDraft draft = draft(100L, SkillDraftDecision.ACCEPTED, "canonical-123");
        when(draftRepository.findByOutcome_OutcomeIdOrderByDraftSkillIdAsc(10))
                .thenReturn(List.of(draft));
        // The publish path spends the draft revision through a compare-and-set before it
        // touches anything. Without this stub the mock returns 0 rows updated, which the
        // service correctly reads as "someone else edited this" and the test never reaches
        // the AI call it is actually about.
        when(learningOutcomeRepository.advanceDraftRevision(10, 1, 3L)).thenReturn(1);

        CourseSkillMapVersion mapVersion = CourseSkillMapVersion.builder()
                .mapVersion(1L)
                .build();
        when(mapVersionRepository.save(any())).thenReturn(mapVersion);
        // No stubs for findById/toResponse: this test asserts the failure path, which throws
        // before the response is ever built. Stubbing them would trip Mockito's strict
        // unnecessary-stubbing check.

        // Simulate a conflict 409 from the AI Service
        doThrow(new AiServiceException(HttpStatus.CONFLICT, "COURSE_MAP_VERSION_CONFLICT", "Version taken", null))
                .when(dataAnalysisClient).publishCourseMap(any());

        // Act & Assert
        DuplicateResourceException ex = assertThrows(DuplicateResourceException.class, () ->
                reviewService.publishLearningOutcome(1, 10, publishRequest(3L)));

        assertEquals("This course map version is already published or conflicts with another map.", ex.getMessage());

        // Verify the format of the courseMapVersion sent to AI Service
        ArgumentCaptor<PublishCourseMapRequest> requestCaptor = ArgumentCaptor.forClass(PublishCourseMapRequest.class);
        verify(dataAnalysisClient).publishCourseMap(requestCaptor.capture());

        PublishCourseMapRequest capturedRequest = requestCaptor.getValue();
        // It must be globally qualified: outcomeId + "-v" + mapVersion (10-v1)
        assertEquals("10-v1", capturedRequest.getCourseMapVersion());
    }

    private static PublishLearningOutcomeRequest publishRequest(Long revision) {
        PublishLearningOutcomeRequest r = new PublishLearningOutcomeRequest();
        r.setExpectedDraftRevision(revision);
        return r;
    }

    private LearningOutcomeSkillDraft draft(Long id, SkillDraftDecision decision, String canonicalId) {
        return LearningOutcomeSkillDraft.builder()
                .draftSkillId(id)
                .outcome(outcome)
                .term("term " + id)
                .canonicalSkillId(canonicalId)
                .canonicalLabel(canonicalId == null ? null : "Label " + canonicalId)
                .level("beginner")
                .weight(java.math.BigDecimal.ONE)
                .evidenceCount(1)
                .decision(decision)
                .rowVersion(0L)
                .build();
    }
}
