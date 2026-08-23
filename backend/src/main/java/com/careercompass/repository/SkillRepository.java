package com.careercompass.repository;

import com.careercompass.entity.Skill;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `skills`.
 * Part of the skills ontology (Section 5.3.2).
 */
public interface SkillRepository extends JpaRepository<Skill, Integer> {

    Optional<Skill> findBySkillName(String skillName);

    List<Skill> findBySkillNameIn(List<String> skillNames);

    boolean existsBySkillName(String skillName);
}
