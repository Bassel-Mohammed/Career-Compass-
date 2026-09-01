package com.careercompass.repository;

import com.careercompass.entity.LearningOutcome;
import com.careercompass.entity.LearningOutcomeExtractionStatus;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `learning_outcomes`.
 * Uploaded by Content Manager (FR-CM-04); consumed by the AI service to build the
 * course -> skill map (Section 5.3.2, Knowledge Base).
 */
public interface LearningOutcomeRepository extends JpaRepository<LearningOutcome, Integer> {

    List<LearningOutcome> findByUniversityField_UniversityFieldId(Integer universityFieldId);

    List<LearningOutcome> findByUploadedByContentManager_ContentManagerId(Integer contentManagerId);

    List<LearningOutcome> findByUploadedByContentManager_ContentManagerIdOrderByUploadedAtDesc(
            Integer contentManagerId);

    /** Ownership-scoped aggregate lookup for every Content Manager mutation. */
    @EntityGraph(attributePaths = {
            "uploadedByContentManager", "universityField",
            "universityField.university", "universityField.studyField"
    })
    Optional<LearningOutcome> findByOutcomeIdAndUploadedByContentManager_ContentManagerId(
            Integer outcomeId, Integer contentManagerId);

    Optional<LearningOutcome> findByAiExtractionId(String aiExtractionId);

    /**
     * Content-level duplicate probe for uploads. The AI service dedupes extractions by
     * document hash, so identical PDF content always maps back to one
     * {@code ai_extraction_id} — which {@code uq_learning_outcomes_ai_extraction} allows
     * on exactly one row.
     */
    Optional<LearningOutcome> findFirstByContentSha256OrderByUploadedAtDesc(String contentSha256);

    List<LearningOutcome> findByUploadedByContentManager_ContentManagerIdAndExtractionStatus(
            Integer contentManagerId, LearningOutcomeExtractionStatus extractionStatus);

    /**
     * Aggregate-level compare-and-swap. A caller receives {@code 1} only when its draft revision
     * is current; {@code 0} means another browser or worker changed the review first.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update LearningOutcome lo
               set lo.draftRevision = lo.draftRevision + 1,
                   lo.updatedAt = CURRENT_TIMESTAMP
             where lo.outcomeId = :outcomeId
               and lo.uploadedByContentManager.contentManagerId = :contentManagerId
               and lo.draftRevision = :expectedRevision
            """)
    int advanceDraftRevision(
            @Param("outcomeId") Integer outcomeId,
            @Param("contentManagerId") Integer contentManagerId,
            @Param("expectedRevision") Long expectedRevision);

    List<LearningOutcome> findByIsDeletedFromDisk(Boolean isDeletedFromDisk);
}
