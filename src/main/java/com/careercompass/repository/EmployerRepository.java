package com.careercompass.repository;

import com.careercompass.entity.Employer;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `employers`.
 * findByEmail supports FR-EMP-01 (register — uniqueness) / FR-EMP-02 (login) / FR-EMP-14.
 */
public interface EmployerRepository extends JpaRepository<Employer, Integer> {

    Optional<Employer> findByEmail(String email);

    boolean existsByEmail(String email);
}
