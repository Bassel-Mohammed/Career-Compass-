package com.careercompass.service;

import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.mapper.ContentManagerMapper;
import com.careercompass.mapper.LearningOutcomeMapper;
import com.careercompass.repository.ContentManagerRepository;
import com.careercompass.repository.LearningOutcomeRepository;
import com.careercompass.repository.StudyFieldRepository;
import com.careercompass.repository.UniversityStudyFieldRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for LearningOutcomeService (FR-CM-04/05). Focused on: the study-field
 * precondition, the get-or-create UniversityStudyField resolution described in the service's
 * Javadoc, and the ownership check on deleteRawFile.
 */
@ExtendWith(MockitoExtension.class)
class LearningOutcomeServiceTest {

    @Mock private ContentManagerRepository contentManagerRepository;
    @Mock private StudyFieldRepository studyFieldRepository;
    @Mock private UniversityStudyFieldRepository universityStudyFieldRepository;
    @Mock private LearningOutcomeRepository learningOutcomeRepository;
    @Mock private FileStorageService fileStorageService;
    @Mock private ContentManagerMapper contentManagerMapper;
    @Mock private LearningOutcomeMapper learningOutcomeMapper;

    @InjectMocks
    private LearningOutcomeService learningOutcomeService;

    // Purpose: Upload Learning Outcome - throws When Study Field Not Selected.
    @Test
    void uploadLearningOutcome_throwsWhenStudyFieldNotSelected() {
        ContentManager cm = ContentManager.builder().contentManagerId(1).studyField(null).build();
        when(contentManagerRepository.findById(1)).thenReturn(Optional.of(cm));

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(1, "CS101", "desc", file))
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
        when(fileStorageService.store(any())).thenReturn("/fake/path/uuid.pdf");
        when(learningOutcomeRepository.save(any(LearningOutcome.class))).thenAnswer(inv -> inv.getArgument(0));
        when(learningOutcomeMapper.toResponse(any(LearningOutcome.class)))
                .thenReturn(LearningOutcomeResponse.builder().courseName("CS101").build());

        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.pdf", "application/pdf", "content".getBytes());

        LearningOutcomeResponse response =
                learningOutcomeService.uploadLearningOutcome(1, "CS101", "desc", file);

        assertThat(response.getCourseName()).isEqualTo("CS101");
        verify(universityStudyFieldRepository, never()).save(any()); // reused existing row, no duplicate
        verify(learningOutcomeRepository).save(argThat(lo -> lo.getUniversityField() == existingUsf));
    }

    // Purpose: Upload Learning Outcome - rejects Non Pdf File.
    @Test
    void uploadLearningOutcome_rejectsNonPdfFile() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "outcomes.txt", "text/plain", "content".getBytes());

        assertThatThrownBy(() -> learningOutcomeService.uploadLearningOutcome(1, "CS101", "desc", file))
                .isInstanceOf(IllegalArgumentException.class);
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
