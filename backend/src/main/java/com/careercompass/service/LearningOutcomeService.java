package com.careercompass.service;

import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.LearningOutcome;
import com.careercompass.entity.StudyField;
import com.careercompass.entity.UniversityStudyField;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.mapper.ContentManagerMapper;
import com.careercompass.mapper.LearningOutcomeMapper;
import com.careercompass.repository.ContentManagerRepository;
import com.careercompass.repository.LearningOutcomeRepository;
import com.careercompass.repository.StudyFieldRepository;
import com.careercompass.repository.UniversityStudyFieldRepository;
import com.careercompass.util.FileValidationUtils;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * Business Layer for a Content Manager's OWN actions (FR-CM-04/05).
 *
 * <p><b>Resolving which course context an upload belongs to:</b> `learning_outcomes` is keyed
 * by `university_field_id` (a {@link UniversityStudyField} row — a specific university +
 * study field + degree-level combination), not directly by study field. Rather than building
 * a separate admin/CM flow to explicitly create/select these combinations (which no FR
 * describes), this service auto-resolves (get-or-creates) the `UniversityStudyField` row
 * matching the Content Manager's OWN university and selected study field — the two pieces of
 * data already on their account (FR-CM-05, FR-SA-03). This keeps the upload flow to a single
 * step for the Content Manager, consistent with the get-or-create pattern already used for
 * skills/levels/statuses elsewhere in this project, rather than introducing a new
 * unrequested CRUD surface.
 */
@Service
@RequiredArgsConstructor
public class LearningOutcomeService {

    private static final long MAX_FILE_SIZE_BYTES = 10L * 1024 * 1024; // same NFR-PERF-07 cap as transcripts

    private final ContentManagerRepository contentManagerRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final UniversityStudyFieldRepository universityStudyFieldRepository;
    private final LearningOutcomeRepository learningOutcomeRepository;
    private final FileStorageService fileStorageService;
    private final ContentManagerMapper contentManagerMapper;
    private final LearningOutcomeMapper learningOutcomeMapper;

    /** FR-CM-05: select the study field the Content Manager teaches in. */
    @Transactional
    public ContentManagerResponse selectStudyField(Integer contentManagerId, Integer studyFieldId) {
        ContentManager contentManager = getOrThrow(contentManagerId);

        StudyField studyField = studyFieldRepository.findById(studyFieldId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Study field with id " + studyFieldId + " not found."));

        contentManager.setStudyField(studyField);
        return contentManagerMapper.toResponse(contentManagerRepository.save(contentManager));
    }

    /** FR-CM-04: upload a course learning-outcome PDF. */
    @Transactional
    public LearningOutcomeResponse uploadLearningOutcome(
            Integer contentManagerId, String courseName, String description, MultipartFile file) {

        FileValidationUtils.validatePdf(file, MAX_FILE_SIZE_BYTES);

        ContentManager contentManager = getOrThrow(contentManagerId);

        if (contentManager.getStudyField() == null) {
            throw new PrerequisiteNotMetException(
                    "Select your study field (FR-CM-05) before uploading learning outcomes.");
        }

        UniversityStudyField universityField = resolveUniversityStudyField(contentManager);

        String storedPath = fileStorageService.store(file);

        LearningOutcome learningOutcome = LearningOutcome.builder()
                .universityField(universityField)
                .courseName(courseName)
                .description(description)
                .filePath(storedPath)
                .originalFilename(file.getOriginalFilename())
                .isDeletedFromDisk(false)
                .uploadedByContentManager(contentManager)
                .build();

        return learningOutcomeMapper.toResponse(learningOutcomeRepository.save(learningOutcome));
    }

    /** FR-CM-04 (view list of uploaded course learning outcomes). */
    @Transactional(readOnly = true)
    public List<LearningOutcomeResponse> listMyUploads(Integer contentManagerId) {
        return learningOutcomeRepository.findByUploadedByContentManager_ContentManagerId(contentManagerId).stream()
                .map(learningOutcomeMapper::toResponse)
                .toList();
    }

    /**
     * Deletes the raw PDF from disk (not the database row) once it's no longer needed
     * (e.g. after Mohammed's service has extracted the course-to-skill mapping from it) —
     * supports NFR-PRIV-03's "raw transcript PDFs deletable after successful extraction",
     * applied here to learning-outcome PDFs by the same principle. The `learning_outcomes`
     * row and its extracted metadata (course name, description) are retained.
     */
    @Transactional
    public LearningOutcomeResponse deleteRawFile(Integer contentManagerId, Integer outcomeId) {
        LearningOutcome learningOutcome = learningOutcomeRepository.findById(outcomeId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Learning outcome with id " + outcomeId + " not found."));

        if (!learningOutcome.getUploadedByContentManager().getContentManagerId().equals(contentManagerId)) {
            throw new UnauthorizedActionException(
                    "You do not have permission to modify this learning outcome.");
        }

        if (!learningOutcome.getIsDeletedFromDisk()) {
            fileStorageService.deleteIfExists(learningOutcome.getFilePath());
            learningOutcome.setIsDeletedFromDisk(true);
            learningOutcome = learningOutcomeRepository.save(learningOutcome);
        }

        return learningOutcomeMapper.toResponse(learningOutcome);
    }

    private UniversityStudyField resolveUniversityStudyField(ContentManager contentManager) {
        return universityStudyFieldRepository
                .findByUniversity_UniversityIdAndStudyField_StudyFieldId(
                        contentManager.getUniversity().getUniversityId(),
                        contentManager.getStudyField().getStudyFieldId())
                .orElseGet(() -> universityStudyFieldRepository.save(UniversityStudyField.builder()
                        .university(contentManager.getUniversity())
                        .studyField(contentManager.getStudyField())
                        .build()));
    }

    private ContentManager getOrThrow(Integer contentManagerId) {
        return contentManagerRepository.findById(contentManagerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Content manager with id " + contentManagerId + " not found."));
    }
}
