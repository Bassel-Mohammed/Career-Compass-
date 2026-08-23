package com.careercompass.mapper;

import com.careercompass.dto.response.ContentManagerResponse;
import com.careercompass.entity.ContentManager;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

@Mapper(componentModel = "spring")
public interface ContentManagerMapper {

    @Mapping(target = "universityId", source = "university.universityId")
    @Mapping(target = "universityName", source = "university.universityName")
    @Mapping(target = "studyFieldId", source = "studyField.studyFieldId")
    @Mapping(target = "studyFieldName", source = "studyField.fieldName")
    ContentManagerResponse toResponse(ContentManager contentManager);
}
