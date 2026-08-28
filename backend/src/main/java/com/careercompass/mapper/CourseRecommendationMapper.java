package com.careercompass.mapper;

import com.careercompass.dto.response.CourseRecommendationItem;
import com.careercompass.entity.CourseRecommendation;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

/**
 * Maps a persisted {@link CourseRecommendation} entity to {@link CourseRecommendationItem}.
 * `targetedSkillName` and `explanation` are NOT mapped (no corresponding entity columns —
 * see CourseRecommendationItem's Javadoc) and are left null by MapStruct for this direction;
 * they're populated separately, only on the fresh-generation response path, in
 * CourseRecommendationService.
 */
@Mapper(componentModel = "spring")
public interface CourseRecommendationMapper {

    // targetedSkillName and explanation now exist on the entity and map by name, so the
    // previous ignore rules would silently blank the very fields V6 was added to keep.
    CourseRecommendationItem toItem(CourseRecommendation entity);
}
