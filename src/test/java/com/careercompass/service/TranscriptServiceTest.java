package com.careercompass.service;

import com.careercompass.dto.request.ConfirmTranscriptRequest;
import com.careercompass.dto.response.SkillDashboardResponse;
import com.careercompass.dto.response.TranscriptReviewResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.*;
import com.careercompass.repository.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for TranscriptService. Repositories and DataAnalysisClient are mocked
 * (NFR-MNT-07) — this test verifies TranscriptService's own orchestration/validation logic,
 * not the mock AI client's behaviour (covered separately by MockDataAnalysisClientTest,
 * Increment 9) nor real PDF parsing (which happens entirely on the Python side).
 */
@ExtendWith(MockitoExtension.class)
class TranscriptServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private AcademicRecordRepository academicRecordRepository;
    @Mock private SkillRepository skillRepository;
    @Mock private LevelRepository levelRepository;
    @Mock private JobseekerSkillRepository jobseekerSkillRepository;
    @Mock private QuizRepository quizRepository;
    @Mock private DataAnalysisClient dataAnalysisClient;

    @InjectMocks
    private TranscriptService transcriptService;

    // Purpose: Upload And Extract - rejects Non Pdf File.
    @Test
    void uploadAndExtract_rejectsNonPdfFile() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "transcript.txt", "text/plain", "not a pdf".getBytes());

        assertThatThrownBy(() -> transcriptService.uploadAndExtract(1, file))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("PDF");
    }

    // Purpose: Upload And Extract - rejects File Over Size Limit.
    @Test
    void uploadAndExtract_rejectsFileOverSizeLimit() {
        byte[] oversized = new byte[11 * 1024 * 1024]; // 11 MB > 10 MB limit (NFR-PERF-07)
        MockMultipartFile file = new MockMultipartFile(
                "file", "transcript.pdf", "application/pdf", oversized);

        assertThatThrownBy(() -> transcriptService.uploadAndExtract(1, file))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("10 MB");
    }

    // Purpose: Upload And Extract - returns Review Rows Without Persisting Anything.
    @Test
    void uploadAndExtract_returnsReviewRowsWithoutPersistingAnything() {
        MockMultipartFile file = new MockMultipartFile(
                "file", "transcript.pdf", "application/pdf", "fake pdf bytes".getBytes());

        when(dataAnalysisClient.extractTranscript(any(TranscriptExtractionRequest.class)))
                .thenReturn(TranscriptExtractionResponse.builder()
                        .courses(List.of(
                                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                                        .courseCode("CS101").courseName("Intro to Programming")
                                        .grade("A").lowConfidence(false).build(),
                                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                                        .courseCode("CS310").courseName("Operating Systems")
                                        .grade("C").lowConfidence(true).build()
                        ))
                        .build());

        TranscriptReviewResponse response = transcriptService.uploadAndExtract(1, file);

        assertThat(response.getCourses()).hasSize(2);
        assertThat(response.getLowConfidenceCount()).isEqualTo(1);
        verifyNoInteractions(academicRecordRepository, jobSeekerRepository, jobseekerSkillRepository);
    }

    // Purpose: Confirm Transcript - throws When Career Path Not Selected.
    @Test
    void confirmTranscript_throwsWhenCareerPathNotSelected() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(null).build();
        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));

        ConfirmTranscriptRequest request = new ConfirmTranscriptRequest();
        var item = new ConfirmTranscriptRequest.CourseGradeItem();
        item.setCourseName("Data Structures");
        item.setGrade("A");
        request.setCourses(List.of(item));

        assertThatThrownBy(() -> transcriptService.confirmTranscript(1, request))
                .isInstanceOf(PrerequisiteNotMetException.class);

        verify(academicRecordRepository, never()).saveAll(any());
    }

    // Purpose: Confirm Transcript - persists Records And Returns Skill Dashboard.
    @Test
    void confirmTranscript_persistsRecordsAndReturnsSkillDashboard() {
        CareerPath careerPath = CareerPath.builder().careerPathId(1).title("Software Engineer").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(careerPath).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));

        ConfirmTranscriptRequest request = new ConfirmTranscriptRequest();
        var item = new ConfirmTranscriptRequest.CourseGradeItem();
        item.setCourseName("Data Structures");
        item.setGrade("A");
        request.setCourses(List.of(item));

        when(dataAnalysisClient.buildSkillVector(any(BuildSkillVectorRequest.class)))
                .thenReturn(SkillVectorResponse.builder()
                        .skills(List.of(SkillScoreDto.builder()
                                .skillName("Data Structures")
                                .score(BigDecimal.valueOf(90))
                                .build()))
                        .build());

        when(skillRepository.findBySkillName("Data Structures")).thenReturn(Optional.empty());
        when(skillRepository.save(any(Skill.class))).thenAnswer(inv -> {
            Skill s = inv.getArgument(0);
            s.setSkillId(1);
            return s;
        });
        when(levelRepository.findByLevelName("Advanced")).thenReturn(Optional.empty());
        when(levelRepository.save(any(Level.class))).thenAnswer(inv -> {
            Level l = inv.getArgument(0);
            l.setLevelId(1);
            return l;
        });
        when(jobseekerSkillRepository.findById(any())).thenReturn(Optional.empty());
        when(jobseekerSkillRepository.save(any(JobseekerSkill.class))).thenAnswer(inv -> inv.getArgument(0));

        when(dataAnalysisClient.analyzeSkillGap(any(SkillGapAnalysisRequest.class)))
                .thenReturn(SkillGapAnalysisResponse.builder()
                        .overallReadinessPercent(90)
                        .skillGaps(List.of(SkillGapAnalysisResponse.SkillGapItemDto.builder()
                                .skillName("Data Structures")
                                .currentScore(BigDecimal.valueOf(90))
                                .targetScore(BigDecimal.valueOf(75))
                                .classification("Strong")
                                .explanation("Well above target.")
                                .build()))
                        .build());

        SkillDashboardResponse dashboard = transcriptService.confirmTranscript(1, request);

        assertThat(dashboard.getCareerPathTitle()).isEqualTo("Software Engineer");
        assertThat(dashboard.getOverallReadinessPercent()).isEqualTo(90);
        assertThat(dashboard.getSkills()).hasSize(1);
        assertThat(dashboard.getSkills().get(0).getClassification()).isEqualTo("Strong");
        assertThat(dashboard.isBasedOnQuizResults()).isFalse();

        verify(academicRecordRepository).deleteByJobSeeker_JobseekerId(1);
        verify(academicRecordRepository).saveAll(any());
        verify(jobseekerSkillRepository).save(any(JobseekerSkill.class));
    }

    // Purpose: Get Skill Dashboard - throws When No Academic Records Exist.
    @Test
    void getSkillDashboard_throwsWhenNoAcademicRecordsExist() {
        CareerPath careerPath = CareerPath.builder().careerPathId(1).title("Software Engineer").build();
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).careerPath(careerPath).build();

        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));
        when(academicRecordRepository.findByJobSeeker_JobseekerId(1)).thenReturn(List.of());

        assertThatThrownBy(() -> transcriptService.getSkillDashboard(1))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }
}
