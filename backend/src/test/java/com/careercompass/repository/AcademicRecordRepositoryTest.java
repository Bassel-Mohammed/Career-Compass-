package com.careercompass.repository;

import com.careercompass.entity.AcademicRecord;
import com.careercompass.entity.JobSeeker;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

/** Verifies the additive {@code course_code} persistence mapping with an actual H2 round trip. */
@DataJpaTest
@ActiveProfiles("dev")
class AcademicRecordRepositoryTest {

    @Autowired private AcademicRecordRepository academicRecordRepository;
    @Autowired private JobSeekerRepository jobSeekerRepository;
    @Autowired private EntityManager entityManager;

    @Test
    void preservesCourseCodeAcrossPersistenceRoundTrip() {
        JobSeeker jobSeeker = jobSeekerRepository.saveAndFlush(JobSeeker.builder()
                .firstName("Test")
                .lastName("Student")
                .email("course-code-test@example.com")
                .passwordHash("hashed-value-placeholder")
                .build());

        academicRecordRepository.saveAndFlush(AcademicRecord.builder()
                .jobSeeker(jobSeeker)
                .courseCode("CS201")
                .courseName("Data Structures")
                .grade("A")
                .build());
        entityManager.clear();

        assertThat(academicRecordRepository.findByJobSeeker_JobseekerId(jobSeeker.getJobseekerId()))
                .singleElement()
                .satisfies(record -> {
                    assertThat(record.getCourseCode()).isEqualTo("CS201");
                    assertThat(record.getCourseName()).isEqualTo("Data Structures");
                });
    }
}
