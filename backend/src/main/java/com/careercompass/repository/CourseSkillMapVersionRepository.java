package com.careercompass.repository;

import com.careercompass.entity.CourseSkillMapState;
import com.careercompass.entity.CourseSkillMapVersion;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

/** Queries append-only publication history by qualified course identity. */
public interface CourseSkillMapVersionRepository extends JpaRepository<CourseSkillMapVersion, Long> {

    Optional<CourseSkillMapVersion>
            findTopByInstitutionCodeAndCatalogVersionAndCourseCodeAndStateOrderByMapVersionDesc(
                    String institutionCode,
                    String catalogVersion,
                    String courseCode,
                    CourseSkillMapState state);

    List<CourseSkillMapVersion> findBySourceOutcome_OutcomeIdOrderByMapVersionDesc(Integer outcomeId);

    @EntityGraph(attributePaths = {"sourceOutcome", "approvedByContentManager"})
    Optional<CourseSkillMapVersion>
            findByMapIdAndSourceOutcome_UploadedByContentManager_ContentManagerId(
                    Long mapId, Integer contentManagerId);

    @Query("""
            select coalesce(max(v.mapVersion), 0)
              from CourseSkillMapVersion v
             where v.institutionCode = :institutionCode
               and v.catalogVersion = :catalogVersion
               and v.courseCode = :courseCode
            """)
    long findLatestMapVersion(
            @Param("institutionCode") String institutionCode,
            @Param("catalogVersion") String catalogVersion,
            @Param("courseCode") String courseCode);
}
