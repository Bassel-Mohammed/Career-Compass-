package com.careercompass.repository;

import com.careercompass.entity.ContentManager;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `content_managers`.
 * findByEmail supports FR-CM-01 (login) / FR-CM-6 (authenticate).
 * findByUniversity_UniversityId supports FR-SA-03 (assign CM to a university, admin lookup).
 */
public interface ContentManagerRepository extends JpaRepository<ContentManager, Integer> {

    Optional<ContentManager> findByEmail(String email);

    boolean existsByEmail(String email);

    List<ContentManager> findByUniversity_UniversityId(Integer universityId);

    List<ContentManager> findByIsActive(Boolean isActive);
}
