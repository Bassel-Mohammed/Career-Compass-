package com.careercompass.repository;

import com.careercompass.entity.JobSeeker;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Sanity test for the entity/repository mapping — confirms Hibernate can generate a schema
 * from the entities against H2 and that a basic save/find round-trip works.
 *
 * This is intentionally the FIRST test in the project: it validates the Increment 2/3 work
 * (entities + repositories) before any business logic is layered on top.
 */
@DataJpaTest
@ActiveProfiles("dev")
class JobSeekerRepositoryTest {

    @Autowired
    private JobSeekerRepository jobSeekerRepository;

    // Purpose: Saves And Finds Job Seeker By Email.
    @Test
    void savesAndFindsJobSeekerByEmail() {
        JobSeeker jobSeeker = JobSeeker.builder()
                .firstName("Basil")
                .lastName("Mohammad")
                .email("basil@example.com")
                .passwordHash("hashed-value-placeholder")
                .build();

        jobSeekerRepository.save(jobSeeker);

        Optional<JobSeeker> found = jobSeekerRepository.findByEmail("basil@example.com");

        assertThat(found).isPresent();
        assertThat(found.get().getFirstName()).isEqualTo("Basil");
        assertThat(found.get().getJobseekerId()).isNotNull();
        assertThat(found.get().getCreatedAt()).isNotNull(); // set by @PrePersist
    }

    // Purpose: Exists By Email Returns False When Not Present.
    @Test
    void existsByEmailReturnsFalseWhenNotPresent() {
        assertThat(jobSeekerRepository.existsByEmail("nobody@example.com")).isFalse();
    }
}
