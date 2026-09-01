package com.careercompass.repository;

import com.careercompass.entity.Skill;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

/**
 * Data Access Layer for `skills`.
 * Part of the skills ontology (Section 5.3.2).
 */
public interface SkillRepository extends JpaRepository<Skill, Integer> {

    Optional<Skill> findBySkillName(String skillName);

    Optional<Skill> findByCanonicalSkillId(String canonicalSkillId);

    List<Skill> findBySkillNameIn(List<String> skillNames);

    boolean existsBySkillName(String skillName);

    /** Search only taxonomy-addressable skills; mutable labels are never returned as identity. */
    @Query("""
            select s from Skill s
             where s.canonicalSkillId is not null
               and (
                    lower(s.skillName) like lower(concat('%', :query, '%'))
                    or lower(s.canonicalSkillId) like lower(concat('%', :query, '%'))
               )
             order by s.skillName asc
            """)
    Page<Skill> searchCanonicalSkills(@Param("query") String query, Pageable pageable);
}
