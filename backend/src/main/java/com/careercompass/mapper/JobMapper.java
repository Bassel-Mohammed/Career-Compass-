package com.careercompass.mapper;

import com.careercompass.dto.response.JobResponse;
import com.careercompass.entity.Job;
import com.careercompass.entity.Skill;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Maps {@link Job} (entity) to {@link JobResponse} (DTO).
 * Denormalises `employer.companyName` and `studyField.fieldName` onto the response so the
 * frontend doesn't need a second round-trip to display a job card (Figure 5.4.9 in the report).
 */
@Mapper(componentModel = "spring")
public interface JobMapper {

    @Mapping(target = "employerId", source = "employer.employerId")
    @Mapping(target = "companyName", source = "employer.companyName")
    @Mapping(target = "studyFieldId", source = "studyField.studyFieldId")
    @Mapping(target = "studyFieldName", source = "studyField.fieldName")
    @Mapping(target = "skillNames", source = "skills", qualifiedByName = "skillsToNames")
    JobResponse toResponse(Job job);

    @org.mapstruct.Named("skillsToNames")
    default List<String> skillsToNames(Set<Skill> skills) {
        if (skills == null) {
            return List.of();
        }
        return skills.stream()
                .map(Skill::getSkillName)
                .collect(Collectors.toList());
    }
}
