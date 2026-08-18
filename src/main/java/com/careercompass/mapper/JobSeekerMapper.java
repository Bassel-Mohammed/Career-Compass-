package com.careercompass.mapper;

import com.careercompass.dto.response.JobSeekerProfileResponse;
import com.careercompass.entity.JobSeeker;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

/**
 * Maps {@link JobSeeker} (entity) to {@link JobSeekerProfileResponse} (DTO).
 *
 * This is the boundary discussed earlier: the entity carries persistence-only fields
 * (passwordHash, JPA-lazy relationships) that must never reach the API. MapStruct generates
 * the implementation at compile time — no reflection, no manual field-by-field copying to
 * maintain by hand.
 */
@Mapper(componentModel = "spring")
public interface JobSeekerMapper {

    @Mapping(target = "universityId", source = "university.universityId")
    @Mapping(target = "universityName", source = "university.universityName")
    @Mapping(target = "studyFieldId", source = "studyField.studyFieldId")
    @Mapping(target = "studyFieldName", source = "studyField.fieldName")
    @Mapping(target = "careerPathId", source = "careerPath.careerPathId")
    @Mapping(target = "careerPathTitle", source = "careerPath.title")
    JobSeekerProfileResponse toProfileResponse(JobSeeker jobSeeker);
}
