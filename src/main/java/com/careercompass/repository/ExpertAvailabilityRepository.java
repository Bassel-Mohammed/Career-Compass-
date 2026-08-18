package com.careercompass.repository;

import com.careercompass.entity.ExpertAvailability;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * Data Access Layer for `expert_availability`.
 * Supports FR-EX-06 (update availability schedule).
 */
public interface ExpertAvailabilityRepository extends JpaRepository<ExpertAvailability, Integer> {

    List<ExpertAvailability> findByExpert_ExpertId(Integer expertId);

    List<ExpertAvailability> findByExpert_ExpertIdAndDayOfWeek(Integer expertId, Byte dayOfWeek);

    void deleteByExpert_ExpertId(Integer expertId);
}
