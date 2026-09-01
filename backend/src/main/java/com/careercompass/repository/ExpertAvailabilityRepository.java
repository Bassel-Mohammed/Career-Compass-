package com.careercompass.repository;

import com.careercompass.entity.ExpertAvailability;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;

/**
 * Data Access Layer for `expert_availability`.
 * Supports FR-EX-06 (update availability schedule).
 */
public interface ExpertAvailabilityRepository extends JpaRepository<ExpertAvailability, Integer> {

    List<ExpertAvailability> findByExpert_ExpertId(Integer expertId);

    List<ExpertAvailability> findByExpert_ExpertIdAndDayOfWeek(Integer expertId, Byte dayOfWeek);

    /**
     * Every slot for a set of mentors, so the mentor list can attach each one's schedule in a
     * single query instead of one per row.
     */
    @EntityGraph(attributePaths = "expert")
    List<ExpertAvailability> findByExpert_ExpertIdIn(Collection<Integer> expertIds);

    void deleteByExpert_ExpertId(Integer expertId);
}
