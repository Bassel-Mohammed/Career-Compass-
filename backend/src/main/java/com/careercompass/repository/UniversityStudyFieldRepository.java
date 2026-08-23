package com.careercompass.repository;

import com.careercompass.entity.UniversityStudyField;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `university_study_fields`.
 * Used when a Content Manager selects the study field they teach in (FR-CM-05),
 * and when browsing which fields a university offers.
 */
public interface UniversityStudyFieldRepository extends JpaRepository<UniversityStudyField, Integer> {

    List<UniversityStudyField> findByUniversity_UniversityId(Integer universityId);

    Optional<UniversityStudyField> findByUniversity_UniversityIdAndStudyField_StudyFieldId(
            Integer universityId, Integer studyFieldId);
}
