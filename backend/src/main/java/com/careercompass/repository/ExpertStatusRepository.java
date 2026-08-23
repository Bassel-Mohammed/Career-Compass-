package com.careercompass.repository;

import com.careercompass.entity.ExpertStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Data Access Layer for `expert_statuses` (lookup table, e.g. "Active"/"Inactive").
 */
public interface ExpertStatusRepository extends JpaRepository<ExpertStatus, Integer> {

    Optional<ExpertStatus> findByStatusName(String statusName);
}
