package com.careercompass.repository;

import com.careercompass.entity.CourseSkillMapItem;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/** Read/write access to immutable item values belonging to one publication version. */
public interface CourseSkillMapItemRepository extends JpaRepository<CourseSkillMapItem, Long> {

    List<CourseSkillMapItem> findByMapVersion_MapIdOrderByMapItemIdAsc(Long mapId);

    boolean existsByMapVersion_MapIdAndCanonicalSkillId(Long mapId, String canonicalSkillId);
}
