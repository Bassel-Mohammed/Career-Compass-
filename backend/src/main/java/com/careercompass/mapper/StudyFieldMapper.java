package com.careercompass.mapper;

import com.careercompass.dto.response.StudyFieldResponse;
import com.careercompass.entity.StudyField;
import org.mapstruct.Mapper;

@Mapper(componentModel = "spring")
public interface StudyFieldMapper {
    StudyFieldResponse toResponse(StudyField studyField);
}
