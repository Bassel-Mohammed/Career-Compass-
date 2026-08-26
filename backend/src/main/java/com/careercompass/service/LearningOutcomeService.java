package com.careercompass.service;

import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.dto.response.LearningOutcomePreviewResponse;
import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.entity.ContentManager;
import com.careercompass.entity.LearningOutcome;
import com.careercompass.entity.StudyField;
import com.careercompass.entity.UniversityStudyField;
import com.careercompass.exception.DuplicateResourceException;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.entity.LearningOutcomeExtractionStatus;
import com.careercompass.integration.dto.SyllabusPreviewResponse;
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

import java.util.EnumSet;
import java.util.List;
import java.util.Set;

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
    private static final int MAX_COURSE_CODE_LENGTH = 80;
    private static final int MAX_CATALOG_VERSION_LENGTH = 120;

    /** Uploads that occupy the document's extraction identity and block re-uploading its content. */
    private static final Set<LearningOutcomeExtractionStatus> ACTIVE_STATUSES = EnumSet.of(
            LearningOutcomeExtractionStatus.QUEUED,
            LearningOutcomeExtractionStatus.EXTRACTING,
            LearningOutcomeExtractionStatus.READY_FOR_REVIEW,
            LearningOutcomeExtractionStatus.PUBLISHING,
            LearningOutcomeExtractionStatus.PUBLISHED);

    private final ContentManagerRepository contentManagerRepository;
    private final StudyFieldRepository studyFieldRepository;
    private final UniversityStudyFieldRepository universityStudyFieldRepository;
    private final LearningOutcomeRepository learningOutcomeRepository;
    private final FileStorageService fileStorageService;
    private final ContentManagerMapper contentManagerMapper;
    private final LearningOutcomeMapper learningOutcomeMapper;
    private final LearningOutcomeReviewService reviewService;

    /**
     * FR-CM-06: the Content Manager's own account.
     *
     * <p>Sits here rather than on {@code ContentManagerAdminService} for the reason that class's
     * Javadoc gives: this is the actor acting on themselves, not an administrator managing them.
     * Its counterpart {@link #selectStudyField} — the only other thing a Content Manager can do
     * to their own account — is already here.
     *
     * <p>Without this, a Content Manager could not read their own profile at all: every other
     * producer of {@link ContentManagerResponse} is behind {@code /api/admin/**}, and the only
     * one they could reach was {@code selectStudyField}, which is a mutation. A UI had no way to
     * show who they were or whether they had already chosen a field without changing something.
     */
    @Transactional(readOnly = true)
    public ContentManagerResponse getMyProfile(Integer contentManagerId) {
        return contentManagerMapper.toResponse(getOrThrow(contentManagerId));
    }

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

    /**
     * FR-CM-04: upload a course learning-outcome PDF and start its skill extraction.
     *
     * <p>The qualified course identity ({@code courseCode} + {@code catalogVersion}, scoped by
     * the Content Manager's own institution) is supplied by the caller rather than inferred
     * from a filename or PDF text — guessing an identity that later becomes a published
     * course key is how silent data corruption happens. The upload answers 201 with the row
     * in {@code QUEUED}/{@code EXTRACTING}/{@code READY_FOR_REVIEW} (or {@code FAILED} when
     * the AI submission itself failed); extraction problems are job statuses, never upload
     * failures, because the file is already safe on disk.
     *
     * <p>The AI call is proposal-only ({@code storeResults=false}): nothing it returns is
     * visible to student analysis until the content manager approves and publishes it.
     */
    @Transactional
    public LearningOutcomeResponse uploadLearningOutcome(
            Integer contentManagerId, String courseCode, String catalogVersion,
            String courseName, String description, MultipartFile file) {

        FileValidationUtils.validatePdf(file, MAX_FILE_SIZE_BYTES);
        String normalizedCourseCode = requireBounded(courseCode, MAX_COURSE_CODE_LENGTH, "course code");
        String normalizedCatalogVersion =
                requireBounded(catalogVersion, MAX_CATALOG_VERSION_LENGTH, "catalog version");

        ContentManager contentManager = getOrThrow(contentManagerId);

        if (contentManager.getStudyField() == null) {
            throw new PrerequisiteNotMetException(
                    "Select your study field (FR-CM-05) before uploading learning outcomes.");
        }

        UniversityStudyField universityField = resolveUniversityStudyField(contentManager);

        byte[] content = fileBytes(file);
        String institutionCode = institutionCodeFor(contentManager);

        learningOutcomeRepository
                .findByUploadedByContentManager_ContentManagerId(contentManagerId).stream()
                .filter(existing -> existing.getInstitutionCode().equals(institutionCode))
                .filter(existing -> existing.getCatalogVersion().equalsIgnoreCase(normalizedCatalogVersion))
                .filter(existing -> existing.getCourseCode().equalsIgnoreCase(normalizedCourseCode))
                .filter(existing -> existing.getExtractionStatus() != LearningOutcomeExtractionStatus.CANCELLED
                        && existing.getExtractionStatus() != LearningOutcomeExtractionStatus.FAILED)
                .findFirst()
                .ifPresent(existing -> {
                    throw new DuplicateResourceException(
                            "A learning outcome for " + normalizedCourseCode + " (catalog "
                                    + normalizedCatalogVersion + ") already exists. Review it instead of re-uploading.");
                });

        // Same PDF content under a different course code still maps to the one extraction
        // the AI service keeps for that document, so reject it before any submission —
        // otherwise the unique ai_extraction_id constraint fails mid-transaction.
        learningOutcomeRepository
                .findFirstByContentSha256OrderByUploadedAtDesc(
                        LearningOutcomeReviewService.sha256Hex(content))
                .filter(existing -> ACTIVE_STATUSES.contains(existing.getExtractionStatus()))
                .ifPresent(existing -> {
                    throw new DuplicateResourceException(
                            "This syllabus PDF was already uploaded as " + existing.getCourseCode()
                                    + " (catalog " + existing.getCatalogVersion()
                                    + "). Review that upload instead of re-uploading the same file.");
                });

        LearningOutcome learningOutcome = learningOutcomeRepository.save(LearningOutcome.builder()
                .universityField(universityField)
                .institutionCode(institutionCode)
                .catalogVersion(normalizedCatalogVersion)
                .courseCode(normalizedCourseCode)
                .contentSha256(LearningOutcomeReviewService.sha256Hex(content))
                .courseName(courseName)
                .description(description)
                .filePath(fileStorageService.store(file))
                .originalFilename(file.getOriginalFilename())
                .extractionStatus(LearningOutcomeExtractionStatus.QUEUED)
                .isDeletedFromDisk(false)
                .uploadedByContentManager(contentManager)
                .build());

        reviewService.beginExtraction(learningOutcome, content, learningOutcome.getOriginalFilename(),
                file.getContentType(), false);

        return reviewService.toResponse(learningOutcome);
    }

    /**
     * Read-only PDF scan behind the upload form's auto-fill. Validates the file exactly
     * like an upload would, then asks the AI service for the course identity printed on
     * the document. Nothing is stored and no extraction is queued.
     */
    @Transactional(readOnly = true)
    public LearningOutcomePreviewResponse previewPdf(Integer contentManagerId, MultipartFile file) {
        getOrThrow(contentManagerId);
        FileValidationUtils.validatePdf(file, MAX_FILE_SIZE_BYTES);
        byte[] content = fileBytes(file);
        SyllabusPreviewResponse wire = reviewService.previewSyllabusPdf(
                file.getOriginalFilename(), file.getContentType(), content);
        return LearningOutcomePreviewResponse.builder()
                .courseCode(wire.getCourseCode())
                .courseName(wire.getCourseTitle())
                .description(wire.getDescription())
                .contentSha256(wire.getContentSha256())
                .totalTerms(wire.getTotalTerms())
                .warnings(wire.getWarnings() == null ? List.of() : wire.getWarnings())
                .build();
    }

    /** FR-CM-04 (view list of uploaded course learning outcomes). */
    @Transactional(readOnly = true)
    public List<LearningOutcomeResponse> listMyUploads(Integer contentManagerId) {
        return learningOutcomeRepository
                .findByUploadedByContentManager_ContentManagerIdOrderByUploadedAtDesc(contentManagerId)
                .stream()
                .map(reviewService::toResponse)
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

    /**
     * Stable qualified identity for the Content Manager's institution. Universities have no
     * natural code in this system, so the surrogate key is used verbatim; the {@code uni:}
     * prefix keeps it readable and distinct from the {@code legacy:*} values migration V5
     * wrote for pre-existing rows.
     */
    private static String institutionCodeFor(ContentManager contentManager) {
        return "uni:" + contentManager.getUniversity().getUniversityId();
    }

    private static byte[] fileBytes(MultipartFile file) {
        try {
            byte[] content = file.getBytes();
            if (content == null || content.length == 0) {
                throw new IllegalArgumentException("The uploaded file is empty.");
            }
            return content;
        } catch (java.io.IOException ex) {
            throw new IllegalStateException("Could not read the uploaded file.", ex);
        }
    }

    private static String requireBounded(String value, int maxLength, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("A " + label + " is required.");
        }
        String trimmed = value.trim();
        if (trimmed.length() > maxLength) {
            throw new IllegalArgumentException(
                    "The " + label + " must be " + maxLength + " characters or fewer.");
        }
        return trimmed;
    }

    private ContentManager getOrThrow(Integer contentManagerId) {
        return contentManagerRepository.findById(contentManagerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Content manager with id " + contentManagerId + " not found."));
    }
}
