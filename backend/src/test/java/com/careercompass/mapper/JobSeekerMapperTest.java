package com.careercompass.mapper;

import com.careercompass.dto.response.JobSeekerProfileResponse;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.JobSeeker;
import com.careercompass.entity.StudyField;
import com.careercompass.entity.University;
import org.junit.jupiter.api.Test;
import org.mapstruct.factory.Mappers;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit test for the MapStruct-generated JobSeekerMapper implementation.
 * Confirms nested relationship fields (university, studyField, careerPath) flatten correctly
 * onto the response DTO, and that no exception is thrown when those relationships are null
 * (a job seeker may not have selected a career path yet — FR-JS-09 is optional at registration).
 */
class JobSeekerMapperTest {

    private final JobSeekerMapper mapper = Mappers.getMapper(JobSeekerMapper.class);

    // Purpose: Maps All Fields Including Nested Relationships.
    @Test
    void mapsAllFieldsIncludingNestedRelationships() {
        JobSeeker jobSeeker = JobSeeker.builder()
                .jobseekerId(1)
                .firstName("Basil")
                .lastName("Mohammad")
                .email("basil@example.com")
                .passwordHash("should-never-appear-in-dto")
                .university(University.builder().universityId(10).universityName("MEU").build())
                .studyField(StudyField.builder().studyFieldId(20).fieldName("Computer Science").build())
                .careerPath(CareerPath.builder().careerPathId(30).title("Software Engineer").build())
                .build();

        JobSeekerProfileResponse response = mapper.toProfileResponse(jobSeeker);

        assertThat(response.getJobseekerId()).isEqualTo(1);
        assertThat(response.getFirstName()).isEqualTo("Basil");
        assertThat(response.getEmail()).isEqualTo("basil@example.com");
        assertThat(response.getUniversityId()).isEqualTo(10);
        assertThat(response.getUniversityName()).isEqualTo("MEU");
        assertThat(response.getStudyFieldId()).isEqualTo(20);
        assertThat(response.getCareerPathTitle()).isEqualTo("Software Engineer");
    }

    // Purpose: Handles Null Career Path Gracefully.
    @Test
    void handlesNullCareerPathGracefully() {
        JobSeeker jobSeeker = JobSeeker.builder()
                .jobseekerId(2)
                .firstName("New")
                .lastName("User")
                .email("new@example.com")
                .passwordHash("hash")
                .careerPath(null) // not selected yet
                .build();

        JobSeekerProfileResponse response = mapper.toProfileResponse(jobSeeker);

        assertThat(response.getCareerPathId()).isNull();
        assertThat(response.getCareerPathTitle()).isNull();
    }
}
