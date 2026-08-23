package com.careercompass.repository;

import com.careercompass.entity.Expert;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `experts`.
 * findByEmail supports FR-EX-01 (login) / FR-EX-13 (authenticate).
 * findByStudyField_StudyFieldIdAndStatus_StatusName supports FR-JS-24
 * (job seeker views available mentors in the same field, filtered by "Active" status).
 */
public interface ExpertRepository extends JpaRepository<Expert, Integer> {

    Optional<Expert> findByEmail(String email);

    boolean existsByEmail(String email);

    List<Expert> findByStudyField_StudyFieldIdAndStatus_StatusName(Integer studyFieldId, String statusName);

    List<Expert> findByStatus_StatusName(String statusName);
}
