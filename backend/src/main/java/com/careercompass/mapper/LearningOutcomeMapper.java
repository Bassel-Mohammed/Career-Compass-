package com.careercompass.mapper;

import com.careercompass.dto.response.LearningOutcomeResponse;
import com.careercompass.entity.LearningOutcome;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring", uses = JsonColumnMapper.class)
public interface LearningOutcomeMapper {

    @Mapping(target = "universityName", source = "universityField.university.universityName")
    @Mapping(target = "studyFieldName", source = "universityField.studyField.fieldName")
    @Mapping(target = "deletedFromDisk", source = "isDeletedFromDisk")
    @Mapping(target = "warnings", source = "extractionWarningsJson", qualifiedByName = "jsonStringList")
    @Mapping(target = "totalSkills", constant = "0L")
    @Mapping(target = "pendingSkills", constant = "0L")
    LearningOutcomeResponse toResponse(LearningOutcome entity);

    @Mapping(target = "universityName", source = "entity.universityField.university.universityName")
    @Mapping(target = "studyFieldName", source = "entity.universityField.studyField.fieldName")
    @Mapping(target = "deletedFromDisk", source = "entity.isDeletedFromDisk")
    @Mapping(target = "warnings", source = "entity.extractionWarningsJson",
            qualifiedByName = "jsonStringList")
    @Mapping(target = "totalSkills", source = "totalSkills")
    @Mapping(target = "pendingSkills", source = "pendingSkills")
    LearningOutcomeResponse toResponse(
            LearningOutcome entity, long totalSkills, long pendingSkills);
}
