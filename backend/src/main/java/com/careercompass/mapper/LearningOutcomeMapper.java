package com.careercompass.mapper;

import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.entity.LearningOutcome;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface LearningOutcomeMapper {

    @Mapping(target = "universityName", source = "universityField.university.universityName")
    @Mapping(target = "studyFieldName", source = "universityField.studyField.fieldName")
    @Mapping(target = "deletedFromDisk", source = "isDeletedFromDisk")
    LearningOutcomeResponse toResponse(LearningOutcome entity);
}
