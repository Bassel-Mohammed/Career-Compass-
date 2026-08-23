package com.careercompass.service;

import com.careercompass.dto.response.CourseRecommendationItem;
import com.careercompass.entity.AcademicRecord;
import com.careercompass.entity.CareerPath;
import com.careercompass.entity.CourseRecommendation;
import com.careercompass.entity.JobSeeker;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.CourseRecommendationRequest;
import com.careercompass.integration.dto.RecommendedCourseDto;
import com.careercompass.mapper.CourseRecommendationMapper;
import com.careercompass.repository.AcademicRecordRepository;
import com.careercompass.repository.CourseRecommendationRepository;
import com.careercompass.repository.JobSeekerRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for CourseRecommendationService.
 *
 * <p>Which skills are weak is now decided by the AI service from the confirmed courses, so these
 * tests cover this service's own job: gathering the courses, clearing stale rows, and preserving
 * the explanation that is returned but never persisted.
 */
@ExtendWith(MockitoExtension.class)
class CourseRecommendationServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private CourseRecommendationRepository courseRecommendationRepository;
    @Mock private AcademicRecordRepository academicRecordRepository;
    @Mock private DataAnalysisClient dataAnalysisClient;
    @Mock private TranscriptService transcriptService;
    @Mock private CourseRecommendationMapper courseRecommendationMapper;

    @InjectMocks
    private CourseRecommendationService courseRecommendationService;

    // Purpose: Generate Recommendations - clears stale rows even when the AI service finds nothing.
    @Test
    void generateRecommendations_returnsEmptyAndClearsStaleRowsWhenAiHasNothingToSuggest() {
        stubJobSeekerWithOneCourse();
        when(dataAnalysisClient.recommendCourses(any(CourseRecommendationRequest.class)))
                .thenReturn(List.of());

        List<CourseRecommendationItem> result = courseRecommendationService.generateRecommendations(1);

        assertThat(result).isEmpty();
        // Stale rows must go regardless: leaving them would show last week's answer as current.
        verify(courseRecommendationRepository).deleteByJobSeeker_JobseekerId(1);
    }

    // Purpose: Generate Recommendations - sends the career path by name, never by numeric id.
    @Test
    void generateRecommendations_sendsCareerPathNameAndCourseCodes() {
        stubJobSeekerWithOneCourse();
        when(dataAnalysisClient.recommendCourses(any(CourseRecommendationRequest.class)))
                .thenReturn(List.of());

        courseRecommendationService.generateRecommendations(1);

        ArgumentCaptor<CourseRecommendationRequest> captor =
                ArgumentCaptor.forClass(CourseRecommendationRequest.class);
        verify(dataAnalysisClient).recommendCourses(captor.capture());

        CourseRecommendationRequest sent = captor.getValue();
        // The AI service keys on the path's name; a database-local integer means nothing to it.
        assertThat(sent.getCareerPathName()).isEqualTo("Software Engineer");
        // course_code is the deterministic join key to the course-skill map.
        assertThat(sent.getCourses()).singleElement()
                .satisfies(c -> assertThat(c.getCourseCode()).isEqualTo("OPS101"));
    }

    // Purpose: Generate Recommendations - persists And Preserves Explanation On Fresh Generation.
    @Test
    void generateRecommendations_persistsAndPreservesExplanationOnFreshGeneration() {
        CareerPath careerPath = CareerPath.builder().careerPathId(1).title("Software Engineer").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(careerPath).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(academicRecordRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of(
                AcademicRecord.builder().courseCode("OPS101").courseName("DevOps").grade("F").build()));
        when(transcriptService.latestQuizScoresBySkillId(1)).thenReturn(Map.of());

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

    /** One job seeker on a career path, with one confirmed course carrying a code. */
    private void stubJobSeekerWithOneCourse() {
        CareerPath careerPath = CareerPath.builder().careerPathId(1).title("Software Engineer").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(careerPath).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(academicRecordRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of(
                AcademicRecord.builder().courseCode("OPS101").courseName("DevOps").grade("F").build()));
        when(transcriptService.latestQuizScoresBySkillId(1)).thenReturn(Map.of());
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
