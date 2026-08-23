package com.careercompass.repository;

import com.careercompass.entity.University;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `universities`.
 */
public interface UniversityRepository extends JpaRepository<University, Integer> {

    Optional<University> findByUniversityName(String universityName);
}
