package com.careercompass.mapper;

import com.careercompass.dto.response.UniversityResponse;
import com.careercompass.entity.University;
import org.mapstruct.Mapper;

@Mapper(componentModel = "spring")
public interface UniversityMapper {
    UniversityResponse toResponse(University university);
}
