package com.careercompass.mapper;

import com.careercompass.dto.response.ExpertResponse;
import com.careercompass.entity.Expert;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface ExpertMapper {

    @Mapping(target = "studyFieldId", source = "studyField.studyFieldId")
    @Mapping(target = "studyFieldName", source = "studyField.fieldName")
    @Mapping(target = "statusName", source = "status.statusName")
    ExpertResponse toResponse(Expert expert);
}
