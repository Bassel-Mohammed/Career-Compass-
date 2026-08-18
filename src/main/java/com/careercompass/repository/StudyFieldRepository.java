package com.careercompass.repository;

import com.careercompass.entity.StudyField;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `study_fields`.
 * Managed by System Administrator (FR-SA-07).
 */
public interface StudyFieldRepository extends JpaRepository<StudyField, Integer> {

    Optional<StudyField> findByFieldName(String fieldName);

    boolean existsByFieldName(String fieldName);
}
