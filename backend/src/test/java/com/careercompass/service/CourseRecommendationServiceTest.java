package com.careercompass.service;

import com.careercompass.dto.response.CourseRecommendationItem;
import com.careercompass.dto.response.SkillDashboardResponse;
import com.careercompass.dto.response.SkillLevelResponse;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.CourseRecommendation;
import com.careercompass.entity.JobSeeker;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.CourseRecommendationRequest;
import com.careercompass.integration.dto.RecommendedCourseDto;
import com.careercompass.mapper.CourseRecommendationMapper;
import com.careercompass.repository.CourseRecommendationRepository;
import com.careercompass.repository.JobSeekerRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for CourseRecommendationService. TranscriptService (used to derive weak skills)
 * is mocked here — its own logic is already covered by TranscriptServiceTest (Increment 10);
 * this test focuses on CourseRecommendationService's own orchestration and the
 * explanation-preservation logic described in its Javadoc.
 */
@ExtendWith(MockitoExtension.class)
class CourseRecommendationServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private CourseRecommendationRepository courseRecommendationRepository;
    @Mock private DataAnalysisClient dataAnalysisClient;
    @Mock private TranscriptService transcriptService;
    @Mock private CourseRecommendationMapper courseRecommendationMapper;

    @InjectMocks
    private CourseRecommendationService courseRecommendationService;

    // Purpose: Generate Recommendations - returns Empty And Clears Stale Rows When No Weak Skills.
    @Test
    void generateRecommendations_returnsEmptyAndClearsStaleRowsWhenNoWeakSkills() {
        CareerPath careerPath = CareerPath.builder().careerPathId(1).title("Software Engineer").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(careerPath).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(transcriptService.getSkillDashboard(1)).thenReturn(SkillDashboardResponse.builder()
                .skills(List.of(SkillLevelResponse.builder()
                        .skillName("Algorithms").classification("Strong").build()))
                .build());

        List<CourseRecommendationItem> result = courseRecommendationService.generateRecommendations(1);

        assertThat(result).isEmpty();
        verify(courseRecommendationRepository).deleteByJobSeeker_JobseekerId(1);
        verify(dataAnalysisClient, never()).recommendCourses(any());
    }

    // Purpose: Generate Recommendations - persists And Preserves Explanation On Fresh Generation.
    @Test
    void generateRecommendations_persistsAndPreservesExplanationOnFreshGeneration() {
        CareerPath careerPath = CareerPath.builder().careerPathId(1).title("Software Engineer").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(careerPath).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(transcriptService.getSkillDashboard(1)).thenReturn(SkillDashboardResponse.builder()
                .skills(List.of(SkillLevelResponse.builder()
                        .skillName("DevOps").classification("Weak").score(BigDecimal.valueOf(30)).build()))
                .build());

        when(dataAnalysisClient.recommendCourses(any(CourseRecommendationRequest.class)))
                .thenReturn(List.of(RecommendedCourseDto.builder()
                        .courseName("CI/CD with GitHub Actions")
                        .sourceLink("https://example.com/cicd")
                        .targetedSkillName("DevOps")
                        .explanation("Directly closes your DevOps gap.")
                        .build()));

        when(courseRecommendationRepository.saveAll(any())).thenAnswer(inv -> {
            List<CourseRecommendation> input = inv.getArgument(0);
            CourseRecommendation entity = input.get(0);
            entity.setRecommendationId(100);
            return input;
        });

        List<CourseRecommendationItem> result = courseRecommendationService.generateRecommendations(1);

        assertThat(result).hasSize(1);
        CourseRecommendationItem item = result.get(0);
        assertThat(item.getRecommendationId()).isEqualTo(100);
        assertThat(item.getCourseName()).isEqualTo("CI/CD with GitHub Actions");
        assertThat(item.getTargetedSkillName()).isEqualTo("DevOps");
        assertThat(item.getExplanation()).isEqualTo("Directly closes your DevOps gap.");

        verify(courseRecommendationRepository).deleteByJobSeeker_JobseekerId(1);
    }

    // Purpose: List Stored Recommendations - delegates To Mapper Without Explanation.
    @Test
    void listStoredRecommendations_delegatesToMapperWithoutExplanation() {
        CourseRecommendation entity = CourseRecommendation.builder()
                .recommendationId(1).courseName("AWS Practitioner").sourceLink("https://example.com/aws")
                .build();

        when(courseRecommendationRepository.findByJobSeeker_JobseekerIdOrderByRecommendedAtDesc(1))
                .thenReturn(List.of(entity));
        when(courseRecommendationMapper.toItem(entity)).thenReturn(CourseRecommendationItem.builder()
                .recommendationId(1).courseName("AWS Practitioner").sourceLink("https://example.com/aws")
                .build());

        List<CourseRecommendationItem> result = courseRecommendationService.listStoredRecommendations(1);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getExplanation()).isNull(); // not persisted, per design
    }
}
