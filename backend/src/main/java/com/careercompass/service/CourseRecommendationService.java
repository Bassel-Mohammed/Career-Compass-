package com.careercompass.service;

import com.careercompass.dto.response.CourseRecommendationItem;
import com.careercompass.entity.AcademicRecord;
import com.careercompass.entity.CourseRecommendation;
import com.careercompass.entity.JobSeeker;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.CourseGradeDto;
import com.careercompass.integration.dto.CourseRecommendationRequest;
import com.careercompass.integration.dto.RecommendedCourseDto;
import com.careercompass.mapper.CourseRecommendationMapper;
import com.careercompass.repository.AcademicRecordRepository;
import com.careercompass.repository.CourseRecommendationRepository;
import com.careercompass.repository.JobSeekerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Business Layer for FR-JS-15/16: course recommendations mapped to identified skill gaps,
 * tailored to the job seeker's selected career path (Module 4, Section 5.3.3).
 *
 * <p>The confirmed courses and quiz evidence go to the AI service, which derives the gaps and
 * retrieves courses against them in one call. Java previously computed a dashboard first and
 * sent the resulting list of weak skill <em>names</em>; that made the recommendation depend on a
 * label surviving a round trip, and produced an empty list whenever it did not. Deriving gaps
 * where the taxonomy lives also means Module 3's and Module 4's answers cannot disagree
 * (Figure 5.3.1.1).
 *
 * <p>Recommendations are retrieved from a curated catalog rather than generated (NFR-AI-05), so
 * every stored row points at a course that exists.
 */
@Service
@RequiredArgsConstructor
public class CourseRecommendationService {

    /** Matches the AI contract's ceiling; the service caps anything larger itself. */
    private static final int MAX_RECOMMENDATIONS = 20;

    private final JobSeekerRepository jobSeekerRepository;
    private final CourseRecommendationRepository courseRecommendationRepository;
    private final AcademicRecordRepository academicRecordRepository;
    private final DataAnalysisClient dataAnalysisClient;
    private final TranscriptService transcriptService;
    private final CourseRecommendationMapper courseRecommendationMapper;

    /**
     * FR-JS-15/16: (re)generate recommendations from the job seeker's CURRENT weak skills,
     * replacing any previously stored recommendations. This is the only path that returns
     * `targetedSkillName`/`explanation` populated — see CourseRecommendationItem's Javadoc.
     */
    @Transactional
    public List<CourseRecommendationItem> generateRecommendations(Integer jobseekerId) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Job seeker with id " + jobseekerId + " not found."));

        if (jobSeeker.getCareerPath() == null) {
            throw new PrerequisiteNotMetException(
                    "Select a career path (FR-JS-09) before generating course recommendations.");
        }

        List<AcademicRecord> records = academicRecordRepository.findByJobSeeker_JobseekerId(jobseekerId);
        if (records.isEmpty()) {
            throw new PrerequisiteNotMetException(
                    "Upload and confirm your transcript (FR-JS-10/11) before generating recommendations.");
        }

        List<CourseGradeDto> courses = records.stream()
                .map(r -> CourseGradeDto.builder()
                        .courseCode(r.getCourseCode())
                        .courseName(r.getCourseName())
                        .grade(r.getGrade())
                        .build())
                .toList();

        CourseRecommendationRequest request = CourseRecommendationRequest.builder()
                .careerPathName(jobSeeker.getCareerPath().getTitle())
                .courses(courses)
                .quizScores(transcriptService.latestQuizScoresBySkillId(jobseekerId))
                .limit(MAX_RECOMMENDATIONS)
                .build();

        // An empty list is a valid outcome — the student may have no gaps the catalog can serve.
        // Stale rows are cleared either way so the view never shows last week's answer.
        List<RecommendedCourseDto> recommended = dataAnalysisClient.recommendCourses(request);

        courseRecommendationRepository.deleteByJobSeeker_JobseekerId(jobseekerId);

        // The targeted skill and explanation are stored alongside the course now. They are the
        // part a student actually reads — "29% of postings ask for this and your coursework
        // shows no evidence of it" — and dropping them on save meant the saved view could only
        // list bare links and suggest regenerating to see the reasoning again.
        List<CourseRecommendation> toSave = recommended.stream()
                .map(r -> CourseRecommendation.builder()
                        .jobSeeker(jobSeeker)
                        .courseName(r.getCourseName())
                        .sourceLink(r.getSourceLink())
                        .targetedSkillName(r.getTargetedSkillName())
                        .explanation(r.getExplanation())
                        .build())
                .toList();

        return courseRecommendationRepository.saveAll(toSave).stream()
                .map(courseRecommendationMapper::toItem)
                .toList();
    }

    /** FR-JS-15: view previously generated recommendations, reasoning included. */
    @Transactional(readOnly = true)
    public List<CourseRecommendationItem> listStoredRecommendations(Integer jobseekerId) {
        return courseRecommendationRepository
                .findByJobSeeker_JobseekerIdOrderByRecommendedAtDesc(jobseekerId).stream()
                .map(courseRecommendationMapper::toItem)
                .toList();
    }
}
