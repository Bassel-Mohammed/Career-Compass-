package com.careercompass.mapper;

import com.careercompass.dto.response.EmployerProfileResponse;
import com.careercompass.entity.Employer;
import org.mapstruct.Mapper;

/**
 * Maps {@link Employer} (entity) to {@link EmployerProfileResponse} (DTO).
 * `passwordHash` is simply not present on the response DTO, so MapStruct never touches it.
 */
@Mapper(componentModel = "spring")
public interface EmployerMapper {

    EmployerProfileResponse toProfileResponse(Employer employer);
}
