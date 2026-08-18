package com.careercompass.repository;

import com.careercompass.entity.LearningOutcome;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `learning_outcomes`.
 * Uploaded by Content Manager (FR-CM-04); consumed by the AI service to build the
 * course -> skill map (Section 5.3.2, Knowledge Base).
 */
public interface LearningOutcomeRepository extends JpaRepository<LearningOutcome, Integer> {

    List<LearningOutcome> findByUniversityField_UniversityFieldId(Integer universityFieldId);

    List<LearningOutcome> findByUploadedByContentManager_ContentManagerId(Integer contentManagerId);

    List<LearningOutcome> findByIsDeletedFromDisk(Boolean isDeletedFromDisk);
}
