package com.careercompass.service;

import com.careercompass.dto.response.LearningOutcomePreviewResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.integration.dto.SyllabusPreviewResponse;
import com.careercompass.mapper.ContentManagerMapper;
import com.careercompass.mapper.LearningOutcomeMapper;
import com.careercompass.repository.ContentManagerRepository;
import com.careercompass.repository.LearningOutcomeRepository;
import com.careercompass.repository.LearningOutcomeSkillDraftRepository;
import com.careercompass.repository.StudyFieldRepository;
import com.careercompass.repository.UniversityStudyFieldRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for LearningOutcomeService (FR-CM-04/05). Focused on: the study-field
 * precondition, the get-or-create UniversityStudyField resolution described in the service's
 * Javadoc, the ownership check on deleteRawFile, and the qualified-identity rules introduced
 * with the review workflow (required course code/catalog version, duplicate rejection).
 */
@ExtendWith(MockitoExtension.class)
class LearningOutcomeServiceTest {

    @Mock private ContentManagerRepository contentManagerRepository;
    @Mock private StudyFieldRepository studyFieldRepository;
    @Mock private UniversityStudyFieldRepository universityStudyFieldRepository;
    @Mock private LearningOutcomeRepository learningOutcomeRepository;
    @Mock private LearningOutcomeSkillDraftRepository learningOutcomeSkillDraftRepository;
    @Mock private FileStorageService fileStorageService;
    @Mock private ContentManagerMapper contentManagerMapper;
    @Mock private LearningOutcomeMapper learningOutcomeMapper;
    @Mock private LearningOutcomeReviewService reviewService;

    @InjectMocks
    private LearningOutcomeService learningOutcomeService;

    // Purpose: Upload Learning Outcome - throws When Study Field Not Selected.
    @Test
    void uploadLearningOutcome_throwsWhenStudyFieldNotSelected() {
        ContentManager cm = ContentManager.builder().contentManagerId(1).studyField(null).build();
        when(contentManagerRepository.findById(1)).thenReturn(Optional.of(cm));

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(
                1, "CS101", "2025-2026", "Data Structures", "desc", file))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }

    // Purpose: Upload Learning Outcome - resolves Existing University Study Field Without Creating Duplicate.
    @Test
    void uploadLearningOutcome_resolvesExistingUniversityStudyFieldWithoutCreatingDuplicate() {
        University university = University.builder().universityId(10).universityName("MEU").build();
        StudyField studyField = StudyField.builder().studyFieldId(20).fieldName("Computer Science").build();
        ContentManager cm = ContentManager.builder()
                .contentManagerId(1).university(university).studyField(studyField).build();
        UniversityStudyField existingUsf = UniversityStudyField.builder()
                .universityFieldId(99).university(university).studyField(studyField).build();

        when(contentManagerRepository.findById(1)).thenReturn(Optional.of(cm));
        when(universityStudyFieldRepository.findByUniversity_UniversityIdAndStudyField_StudyFieldId(10, 20))
                .thenReturn(Optional.of(existingUsf));
        when(learningOutcomeRepository.findByUploadedByContentManager_ContentManagerId(1))
                .thenReturn(List.of());
        when(fileStorageService.store(any())).thenReturn("/fake/path/uuid.pdf");
        when(learningOutcomeRepository.save(any(LearningOutcome.class))).thenAnswer(inv -> inv.getArgument(0));
        when(reviewService.toResponse(any(LearningOutcome.class)))
                .thenReturn(LearningOutcomeResponse.builder().courseName("Data Structures").build());

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        LearningOutcomeResponse response = learningOutcomeService.uploadLearningOutcome(
                1, "CS101", "2025-2026", "Data Structures", "desc", file);

        assertThat(response.getCourseName()).isEqualTo("Data Structures");
        verify(universityStudyFieldRepository, never()).save(any()); // reused existing row, no duplicate
        verify(learningOutcomeRepository).save(argThat(lo ->
                lo.getUniversityField() == existingUsf
                        && "CS101".equals(lo.getCourseCode())
                        && "2025-2026".equals(lo.getCatalogVersion())
                        && "uni:10".equals(lo.getInstitutionCode())
                        && lo.getContentSha256() != null
                        && lo.getExtractionStatus() == LearningOutcomeExtractionStatus.QUEUED));
        verify(reviewService).beginExtraction(any(), any(), any(), any(), eq(false));
    }

    // Purpose: Upload Learning Outcome - rejects a duplicate qualified course identity.
    @Test
    void uploadLearningOutcome_rejectsDuplicateCourseIdentity() {
        University university = University.builder().universityId(10).universityName("MEU").build();
        StudyField studyField = StudyField.builder().studyFieldId(20).fieldName("Computer Science").build();
        ContentManager cm = ContentManager.builder()
                .contentManagerId(1).university(university).studyField(studyField).build();
        UniversityStudyField usf = UniversityStudyField.builder()
                .universityFieldId(99).university(university).studyField(studyField).build();
        LearningOutcome existing = LearningOutcome.builder()
                .outcomeId(7)
                .institutionCode("uni:10")
                .catalogVersion("2025-2026")
                .courseCode("CS101")
                .extractionStatus(LearningOutcomeExtractionStatus.READY_FOR_REVIEW)
                .uploadedByContentManager(cm)
                .universityField(usf)
                .build();

        when(contentManagerRepository.findById(1)).thenReturn(Optional.of(cm));
        when(universityStudyFieldRepository.findByUniversity_UniversityIdAndStudyField_StudyFieldId(10, 20))
                .thenReturn(Optional.of(usf));
        when(learningOutcomeRepository.findByUploadedByContentManager_ContentManagerId(1))
                .thenReturn(List.of(existing));

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(
                1, "cs101", "2025-2026", "Data Structures", null, file))
                .isInstanceOf(DuplicateResourceException.class);

        verify(fileStorageService, never()).store(any()); // nothing stored for a rejected duplicate
    }

    // Purpose: Upload Learning Outcome - rejects the same PDF content under a different course
    // identity before submission, because one document maps to exactly one extraction id.
    @Test
    void uploadLearningOutcome_rejectsDuplicatePdfContentUnderDifferentCourse() {
        University university = University.builder().universityId(10).universityName("MEU").build();
        StudyField studyField = StudyField.builder().studyFieldId(20).fieldName("Computer Science").build();
        ContentManager cm = ContentManager.builder()
                .contentManagerId(1).university(university).studyField(studyField).build();
        UniversityStudyField usf = UniversityStudyField.builder()
                .universityFieldId(99).university(university).studyField(studyField).build();
        LearningOutcome sameContentElsewhere = LearningOutcome.builder()
                .outcomeId(7)
                .institutionCode("uni:10")
                .catalogVersion("2025-2026")
                .courseCode("CS999")
                .contentSha256(LearningOutcomeReviewService.sha256Hex("content".getBytes()))
                .extractionStatus(LearningOutcomeExtractionStatus.READY_FOR_REVIEW)
                .uploadedByContentManager(cm)
                .universityField(usf)
                .build();

        when(contentManagerRepository.findById(1)).thenReturn(Optional.of(cm));
        when(universityStudyFieldRepository.findByUniversity_UniversityIdAndStudyField_StudyFieldId(10, 20))
                .thenReturn(Optional.of(usf));
        when(learningOutcomeRepository.findByUploadedByContentManager_ContentManagerId(1))
                .thenReturn(List.of()); // no duplicate course identity for this manager
        when(learningOutcomeRepository.findFirstByContentSha256OrderByUploadedAtDesc(any()))
                .thenReturn(Optional.of(sameContentElsewhere));

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(
                1, "MA201", "2025-2026", "Linear Algebra", null, file))
                .isInstanceOf(DuplicateResourceException.class)
                .hasMessageContaining("CS999");

        verify(fileStorageService, never()).store(any());
        verify(reviewService, never())
                .beginExtraction(any(), any(), any(), any(), anyBoolean());
    }

    // Purpose: Upload Learning Outcome - a FAILED earlier attempt with the same content does not
    // block a corrected re-upload (it never occupies the extraction identity).
    @Test
    void uploadLearningOutcome_allowsReuploadWhenPriorContentRowFailed() {
        University university = University.builder().universityId(10).universityName("MEU").build();
        StudyField studyField = StudyField.builder().studyFieldId(20).fieldName("Computer Science").build();
        ContentManager cm = ContentManager.builder()
                .contentManagerId(1).university(university).studyField(studyField).build();
        UniversityStudyField usf = UniversityStudyField.builder()
                .universityFieldId(99).university(university).studyField(studyField).build();

        when(contentManagerRepository.findById(1)).thenReturn(Optional.of(cm));
        when(universityStudyFieldRepository.findByUniversity_UniversityIdAndStudyField_StudyFieldId(10, 20))
                .thenReturn(Optional.of(usf));
        when(learningOutcomeRepository.findByUploadedByContentManager_ContentManagerId(1))
                .thenReturn(List.of());
        when(learningOutcomeRepository.findFirstByContentSha256OrderByUploadedAtDesc(any()))
                .thenReturn(Optional.empty());
        when(fileStorageService.store(any())).thenReturn("/fake/path/uuid.pdf");
        when(learningOutcomeRepository.save(any(LearningOutcome.class))).thenAnswer(inv -> inv.getArgument(0));
        when(reviewService.toResponse(any(LearningOutcome.class)))
                .thenReturn(LearningOutcomeResponse.builder().courseName("Linear Algebra").build());

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        learningOutcomeService.uploadLearningOutcome(1, "MA201", "2025-2026", "Linear Algebra", null, file);

        verify(reviewService).beginExtraction(any(), any(), any(), any(), eq(false));
    }

    // Purpose: Upload Learning Outcome - rejects Non Pdf File.
    @Test
    void uploadLearningOutcome_rejectsNonPdfFile() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.txt", "text/plain", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(
                1, "CS101", "2025-2026", "Data Structures", "desc", file))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // Purpose: Upload Learning Outcome - a missing course code is a client error, not a guess.
    @Test
    void uploadLearningOutcome_requiresCourseCode() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(
                1, " ", "2025-2026", "Data Structures", null, file))
                .isInstanceOf(IllegalArgumentException.class);
    }

    // Purpose: Upload preview - validates the PDF and maps the AI suggestion without storing
    // anything, so the form auto-fill can never create rows or start extractions.
    @Test
    void previewPdf_mapsSuggestionWithoutStoringAnything() {
        when(contentManagerRepository.findById(1))
                .thenReturn(Optional.of(ContentManager.builder().contentManagerId(1).build()));
        when(reviewService.previewSyllabusPdf(any(), any(), any()))
                .thenReturn(SyllabusPreviewResponse.builder()
                        .courseCode("CS241")
                        .courseTitle("Data Structures")
                        .description("Covers lists, trees, and graphs.")
                        .contentSha256("abc123")
                        .totalTerms(12)
                        .warnings(List.of())
                        .build());

        MockMultipartFile file = new MockMultipartFile(
                "file", "syllabus.pdf", "application/pdf", "content".getBytes());

        LearningOutcomePreviewResponse out = learningOutcomeService.previewPdf(1, file);

        assertThat(out.getCourseCode()).isEqualTo("CS241");
        assertThat(out.getCourseName()).isEqualTo("Data Structures");
        assertThat(out.getDescription()).isEqualTo("Covers lists, trees, and graphs.");
        assertThat(out.getTotalTerms()).isEqualTo(12);
        verify(learningOutcomeRepository, never()).save(any());
        verify(fileStorageService, never()).store(any());
        verify(reviewService, never())
                .beginExtraction(any(), any(), any(), any(), anyBoolean());
    }

    // Purpose: Upload preview - non-PDF files are rejected before the AI call.
    @Test
    void previewPdf_rejectsNonPdfFile() {
        when(contentManagerRepository.findById(1))
                .thenReturn(Optional.of(ContentManager.builder().contentManagerId(1).build()));
        MockMultipartFile file = new MockMultipartFile(
                "file", "syllabus.txt", "text/plain", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.previewPdf(1, file))
                .isInstanceOf(IllegalArgumentException.class);
        verify(reviewService, never()).previewSyllabusPdf(any(), any(), any());
    }

    // Purpose: Delete Outcome - removes the row, its drafts and the file.
    @Test
    void deleteOutcome_removesDraftsAndFileBeforeTheRow() {
        ContentManager owner = ContentManager.builder().contentManagerId(1).build();
        LearningOutcome lo = LearningOutcome.builder()
                .outcomeId(5).uploadedByContentManager(owner)
                .filePath("/uploads/outcomes.pdf").isDeletedFromDisk(false)
                .courseMapVersion(0L).build();
        when(learningOutcomeRepository.findById(5)).thenReturn(Optional.of(lo));

        learningOutcomeService.deleteOutcome(1, 5);

        // Drafts first — there is no cascade, and deleting the parent while children still
        // reference it fails on the foreign key.
        verify(learningOutcomeSkillDraftRepository)
                .deleteByOutcome_OutcomeIdAndOutcome_UploadedByContentManager_ContentManagerId(5, 1);
        verify(fileStorageService).deleteIfExists("/uploads/outcomes.pdf");
        verify(learningOutcomeRepository).delete(lo);
    }

    // Purpose: Delete Outcome - refuses once published, so a live course map keeps its source.
    @Test
    void deleteOutcome_refusesOncePublishedToACourseMap() {
        ContentManager owner = ContentManager.builder().contentManagerId(1).build();
        LearningOutcome lo = LearningOutcome.builder()
                .outcomeId(5).uploadedByContentManager(owner).courseMapVersion(3L).build();
        when(learningOutcomeRepository.findById(5)).thenReturn(Optional.of(lo));

        assertThatThrownBy(() -> learningOutcomeService.deleteOutcome(1, 5))
                .isInstanceOf(PrerequisiteNotMetException.class)
                .hasMessageContaining("published");

        // Nothing is touched: the published map in the AI service is immutable, so removing this
        // row would not retract it — only strip away the record of where its skills came from.
        verify(learningOutcomeRepository, never()).delete(any(LearningOutcome.class));
        verify(fileStorageService, never()).deleteIfExists(any());
        verifyNoInteractions(learningOutcomeSkillDraftRepository);
    }

    // Purpose: Delete Outcome - throws Unauthorized When Caller Did Not Upload It.
    @Test
    void deleteOutcome_throwsUnauthorizedWhenCallerDidNotUploadIt() {
        ContentManager owner = ContentManager.builder().contentManagerId(1).build();
        LearningOutcome lo = LearningOutcome.builder()
                .outcomeId(5).uploadedByContentManager(owner).courseMapVersion(0L).build();
        when(learningOutcomeRepository.findById(5)).thenReturn(Optional.of(lo));

        assertThatThrownBy(() -> learningOutcomeService.deleteOutcome(2, 5))
                .isInstanceOf(UnauthorizedActionException.class);

        verify(learningOutcomeRepository, never()).delete(any(LearningOutcome.class));
        verifyNoInteractions(learningOutcomeSkillDraftRepository);
    }

    // Purpose: Delete Raw File - throws Unauthorized When Caller Did Not Upload It.
    @Test
    void deleteRawFile_throwsUnauthorizedWhenCallerDidNotUploadIt() {
        ContentManager owner = ContentManager.builder().contentManagerId(1).build();
        LearningOutcome lo = LearningOutcome.builder()
                .outcomeId(5).uploadedByContentManager(owner).isDeletedFromDisk(false).build();

        when(learningOutcomeRepository.findById(5)).thenReturn(Optional.of(lo));

        assertThatThrownBy(() -> learningOutcomeService.deleteRawFile(2, 5))
                .isInstanceOf(UnauthorizedActionException.class);

        verify(fileStorageService, never()).deleteIfExists(any());
    }

    // Purpose: Delete Raw File - is Idempotent When Already Deleted.
    @Test
    void deleteRawFile_isIdempotentWhenAlreadyDeleted() {
        ContentManager owner = ContentManager.builder().contentManagerId(1).build();
        LearningOutcome lo = LearningOutcome.builder()
                .outcomeId(5).uploadedByContentManager(owner).isDeletedFromDisk(true).build();

        when(learningOutcomeRepository.findById(5)).thenReturn(Optional.of(lo));
        when(learningOutcomeMapper.toResponse(lo)).thenReturn(LearningOutcomeResponse.builder().build());

        learningOutcomeService.deleteRawFile(1, 5);

        verify(fileStorageService, never()).deleteIfExists(any());
        verify(learningOutcomeRepository, never()).save(any());
    }
}
