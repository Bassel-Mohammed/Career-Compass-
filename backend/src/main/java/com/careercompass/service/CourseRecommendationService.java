package com.careercompass.service;

import com.careercompass.dto.response.CourseRecommendationItem;
import com.careercompass.dto.response.SkillDashboardResponse;
import com.careercompass.dto.response.SkillLevelResponse;
import com.careercompass.entity.CourseRecommendation;
import com.careercompass.entity.JobSeeker;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.CourseRecommendationRequest;
import com.careercompass.integration.dto.RecommendedCourseDto;
import com.careercompass.mapper.CourseRecommendationMapper;
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
 * Depends on {@link TranscriptService#getSkillDashboard} to identify weak skills — reuses
 * that logic rather than duplicating skill-vector/skill-gap computation here, since "which
 * skills are weak" is already fully solved by Increment 10 and recommendations are simply the
 * next step in the same pipeline (Module 3's output feeds Module 4's input, per Figure 5.3.1.1
 * in the report).
 */
@Service
@RequiredArgsConstructor
public class CourseRecommendationService {

    private final JobSeekerRepository jobSeekerRepository;
    private final CourseRecommendationRepository courseRecommendationRepository;
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

        SkillDashboardResponse dashboard = transcriptService.getSkillDashboard(jobseekerId);

        List<String> weakSkillNames = dashboard.getSkills().stream()
                .filter(s -> "Weak".equals(s.getClassification()))
                .map(SkillLevelResponse::getSkillName)
                .toList();

        if (weakSkillNames.isEmpty()) {
            // No gaps to recommend against — clear any stale recommendations and return empty,
            // rather than erroring, since "no weak skills" is a valid (good!) outcome.
            courseRecommendationRepository.deleteByJobSeeker_JobseekerId(jobseekerId);
            return List.of();
        }

        CourseRecommendationRequest request = CourseRecommendationRequest.builder()
                .careerPathId(jobSeeker.getCareerPath().getCareerPathId())
                .weakSkillNames(weakSkillNames)
                .build();

        List<RecommendedCourseDto> recommended = dataAnalysisClient.recommendCourses(request);

        courseRecommendationRepository.deleteByJobSeeker_JobseekerId(jobseekerId);

        List<CourseRecommendation> toSave = recommended.stream()
                .map(r -> CourseRecommendation.builder()
                        .jobSeeker(jobSeeker)
                        .courseName(r.getCourseName())
                        .sourceLink(r.getSourceLink())
                        .build())
                .toList();
        List<CourseRecommendation> saved = courseRecommendationRepository.saveAll(toSave);

        // Re-attach the explanation/targetedSkill (not persisted) to the freshly-saved rows,
        // matched by position — recommended and saved are built from the same source list in
        // the same order, so this is safe here without needing an extra correlation key.
        return zipWithExplanations(saved, recommended);
    }

    /** FR-JS-15: view previously generated recommendations (explanation/targetedSkill are null — see Javadoc). */
    @Transactional(readOnly = true)
    public List<CourseRecommendationItem> listStoredRecommendations(Integer jobseekerId) {
        return courseRecommendationRepository
                .findByJobSeeker_JobseekerIdOrderByRecommendedAtDesc(jobseekerId).stream()
                .map(courseRecommendationMapper::toItem)
                .toList();
    }

    private List<CourseRecommendationItem> zipWithExplanations(
            List<CourseRecommendation> saved, List<RecommendedCourseDto> source) {
        List<CourseRecommendationItem> items = new java.util.ArrayList<>();
        for (int i = 0; i < saved.size(); i++) {
            CourseRecommendation entity = saved.get(i);
            RecommendedCourseDto sourceDto = source.get(i);
            items.add(CourseRecommendationItem.builder()
                    .recommendationId(entity.getRecommendationId())
                    .courseName(entity.getCourseName())
                    .sourceLink(entity.getSourceLink())
                    .targetedSkillName(sourceDto.getTargetedSkillName())
                    .explanation(sourceDto.getExplanation())
                    .recommendedAt(entity.getRecommendedAt())
                    .build());
        }
        return items;
    }
}
