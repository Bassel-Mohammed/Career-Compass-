package com.careercompass.service;

import com.careercompass.dto.request.ConfirmTranscriptRequest;
import com.careercompass.dto.response.SkillDashboardResponse;
import com.careercompass.dto.response.SkillLevelResponse;
import com.careercompass.dto.response.TranscriptReviewResponse;
import com.careercompass.entity.*;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.*;
import com.careercompass.repository.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.math.BigDecimal;
import java.util.Base64;
import java.util.List;

/**
 * Business Layer for FR-JS-10 through FR-JS-14: transcript upload, extraction review,
 * confirmation/persistence, and the resulting skill dashboard.
 *
 * Deliberately split into two steps (upload -&gt; review -&gt; confirm -&gt; persist), matching
 * the report's own UI flow (Figures 5.4.4/5.4.5) and NFR-REL-03 ("confirmed by the student
 * before persistence"). Everything here delegates the actual PDF parsing and skill-vector
 * math to {@link DataAnalysisClient} (Modules 1, 2, 3) — this service's job is orchestration,
 * validation, and persistence, never AI logic itself, matching the Component-level
 * architecture (Integration Layer sits between this Business Layer and the Data Analyses
 * Layer).
 *
 * <p><b>Quiz write-back (FR-JS-20/21/22):</b> {@code recomputeAndPersistSkillDashboard} looks
 * up the latest completed {@link Quiz} whose {@code courseName} matches a skill's name and, if
 * found, uses the quiz score in place of the grade-based estimate for that skill. This reuses
 * the "course name doubles as skill name" simplification already present in the mock AI
 * client's grade-based scoring (Increment 10) — a real skill ontology would map many courses
 * to one skill, and likewise a quiz would need an explicit skill reference rather than being
 * matched by name. Flagged here and in the Increment 12 doc as a schema/design simplification
 * to revisit once real course-to-skill mapping data exists (same category of gap as the
 * `courses_recommendations` schema limitation noted in Increment 11).
 */
@Service
@RequiredArgsConstructor
public class TranscriptService {

    private static final long MAX_FILE_SIZE_BYTES = 10L * 1024 * 1024; // NFR-PERF-07

    private final JobSeekerRepository jobSeekerRepository;
    private final AcademicRecordRepository academicRecordRepository;
    private final SkillRepository skillRepository;
    private final LevelRepository levelRepository;
    private final JobseekerSkillRepository jobseekerSkillRepository;
    private final QuizRepository quizRepository;
    private final DataAnalysisClient dataAnalysisClient;

    /**
     * FR-JS-10: upload and extract. Nothing is persisted here — see class Javadoc.
     */
    public TranscriptReviewResponse uploadAndExtract(Integer jobseekerId, MultipartFile file) {
        validateFile(file);

        String base64Content;
        try {
            base64Content = Base64.getEncoder().encodeToString(file.getBytes());
        } catch (java.io.IOException e) {
            throw new IllegalStateException("Could not read the uploaded file.", e);
        }

        TranscriptExtractionRequest request = TranscriptExtractionRequest.builder()
                .jobseekerId(jobseekerId)
                .fileBase64(base64Content)
                .originalFilename(file.getOriginalFilename())
                .build();

        TranscriptExtractionResponse extraction = dataAnalysisClient.extractTranscript(request);

        List<TranscriptReviewResponse.ExtractedCourseItem> items = extraction.getCourses().stream()
                .map(c -> TranscriptReviewResponse.ExtractedCourseItem.builder()
                        .courseCode(c.getCourseCode())
                        .courseName(c.getCourseName())
                        .grade(c.getGrade())
                        .lowConfidence(c.isLowConfidence())
                        .build())
                .toList();

        long lowConfidenceCount = items.stream().filter(TranscriptReviewResponse.ExtractedCourseItem::isLowConfidence).count();

        return TranscriptReviewResponse.builder()
                .courses(items)
                .lowConfidenceCount((int) lowConfidenceCount)
                .build();
    }

    /**
     * FR-JS-11: persist the (possibly student-corrected) reviewed rows, then immediately
     * compute and persist the Student Skill Vector (Module 2) — this is what FR-JS-12 through
     * FR-JS-14 depend on. Requires a career path to already be selected (FR-JS-09), since the
     * skill vector and target levels are scoped to it.
     */
    @Transactional
    public SkillDashboardResponse confirmTranscript(Integer jobseekerId, ConfirmTranscriptRequest request) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException("Job seeker with id " + jobseekerId + " not found."));

        if (jobSeeker.getCareerPath() == null) {
            throw new PrerequisiteNotMetException(
                    "Select a career path (FR-JS-09) before confirming your transcript.");
        }

        // Replace any previously stored academic records for this job seeker (re-upload flow).
        academicRecordRepository.deleteByJobSeeker_JobseekerId(jobseekerId);

        List<AcademicRecord> records = request.getCourses().stream()
                .map(c -> AcademicRecord.builder()
                        .jobSeeker(jobSeeker)
                        .courseName(c.getCourseName())
                        .grade(c.getGrade())
                        .build())
                .toList();
        academicRecordRepository.saveAll(records);

        return recomputeAndPersistSkillDashboard(jobSeeker, request.getCourses());
    }

    /**
     * FR-JS-14/21: current skill dashboard, recomputed live from the persisted academic
     * records and the AI service — not read from a cached table, so it always reflects the
     * latest grades/career-path selection.
     */
    @Transactional
    public SkillDashboardResponse getSkillDashboard(Integer jobseekerId) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException("Job seeker with id " + jobseekerId + " not found."));

        if (jobSeeker.getCareerPath() == null) {
            throw new PrerequisiteNotMetException(
                    "Select a career path (FR-JS-09) to view your skill dashboard.");
        }

        List<AcademicRecord> records = academicRecordRepository.findByJobSeeker_JobseekerId(jobseekerId);
        if (records.isEmpty()) {
            throw new PrerequisiteNotMetException(
                    "Upload and confirm your transcript (FR-JS-10/11) before viewing your skill dashboard.");
        }

        List<ConfirmTranscriptRequest.CourseGradeItem> courseItems = records.stream()
                .map(r -> {
                    var item = new ConfirmTranscriptRequest.CourseGradeItem();
                    item.setCourseName(r.getCourseName());
                    item.setGrade(r.getGrade());
                    return item;
                })
                .toList();

        return recomputeAndPersistSkillDashboard(jobSeeker, courseItems);
    }

    private SkillDashboardResponse recomputeAndPersistSkillDashboard(
            JobSeeker jobSeeker, List<ConfirmTranscriptRequest.CourseGradeItem> courses) {

        // Module 2: deterministic skill vector, grade-based (FR-JS-22's baseline).
        BuildSkillVectorRequest vectorRequest = BuildSkillVectorRequest.builder()
                .jobseekerId(jobSeeker.getJobseekerId())
                .careerPathId(jobSeeker.getCareerPath().getCareerPathId())
                .courses(courses.stream()
                        .map(c -> CourseGradeDto.builder().courseName(c.getCourseName()).grade(c.getGrade()).build())
                        .toList())
                .build();
        SkillVectorResponse rawSkillVector = dataAnalysisClient.buildSkillVector(vectorRequest);

        // FR-JS-20: apply the quiz write-back on top of the grade-based vector, per skill,
        // before persisting or running the gap analysis — this is the "red dashed loop" from
        // Figure 5.3.1.1 in the report (Quiz module refining the Skill Vector). See this
        // method's class-level Javadoc note on why `courseName` doubles as the skill-matching
        // key for this lookup.
        boolean[] anySkillFromQuiz = {false};
        List<SkillScoreDto> effectiveSkillVector = rawSkillVector.getSkills().stream()
                .map(skill -> {
                    List<Quiz> completedQuizzes = quizRepository
                            .findByJobSeeker_JobseekerIdAndCourseNameIgnoreCaseAndTakenAtIsNotNullOrderByTakenAtDesc(
                                    jobSeeker.getJobseekerId(), skill.getSkillName());
                    if (!completedQuizzes.isEmpty() && completedQuizzes.get(0).getScore() != null) {
                        anySkillFromQuiz[0] = true;
                        return SkillScoreDto.builder()
                                .skillName(skill.getSkillName())
                                .score(completedQuizzes.get(0).getScore())
                                .build();
                    }
                    return skill; // FR-JS-22: no quiz taken -> keep the grade-based score
                })
                .toList();

        // Persist each EFFECTIVE skill score (quiz-refined where applicable) into jobseeker_skills.
        for (SkillScoreDto skillScore : effectiveSkillVector) {
            persistJobseekerSkill(jobSeeker, skillScore);
        }

        // Module 3: skill-gap analysis, run against the effective (possibly quiz-refined) vector.
        SkillGapAnalysisRequest gapRequest = SkillGapAnalysisRequest.builder()
                .careerPathId(jobSeeker.getCareerPath().getCareerPathId())
                .skillVector(effectiveSkillVector)
                .build();
        SkillGapAnalysisResponse gapResponse = dataAnalysisClient.analyzeSkillGap(gapRequest);

        List<SkillLevelResponse> skillLevels = gapResponse.getSkillGaps().stream()
                .sorted((a, b) -> a.getCurrentScore().compareTo(b.getCurrentScore())) // weakest-first, matches Figure 5.4.6
                .map(gap -> SkillLevelResponse.builder()
                        .skillName(gap.getSkillName())
                        .score(gap.getCurrentScore())
                        .classification(gap.getClassification())
                        .explanation(gap.getExplanation())
                        .build())
                .toList();

        return SkillDashboardResponse.builder()
                .jobseekerId(jobSeeker.getJobseekerId())
                .careerPathTitle(jobSeeker.getCareerPath().getTitle())
                .overallReadinessPercent(gapResponse.getOverallReadinessPercent())
                .skills(skillLevels)
                .basedOnQuizResults(anySkillFromQuiz[0]) // FR-JS-20/21 vs FR-JS-22 fallback
                .build();
    }

    private void persistJobseekerSkill(JobSeeker jobSeeker, SkillScoreDto skillScore) {
        Skill skill = getOrCreateSkill(skillScore.getSkillName());
        Level level = getOrCreateLevel(classifyLevel(skillScore.getScore()));

        JobseekerSkillId id = new JobseekerSkillId(jobSeeker.getJobseekerId(), skill.getSkillId());

        JobseekerSkill jobseekerSkill = jobseekerSkillRepository.findById(id)
                .orElse(JobseekerSkill.builder().id(id).jobSeeker(jobSeeker).skill(skill).build());

        jobseekerSkill.setLevel(level);
        jobseekerSkill.setScore(skillScore.getScore());

        jobseekerSkillRepository.save(jobseekerSkill);
    }

    private Skill getOrCreateSkill(String skillName) {
        return skillRepository.findBySkillName(skillName)
                .orElseGet(() -> skillRepository.save(Skill.builder().skillName(skillName).build()));
    }

    private Level getOrCreateLevel(String levelName) {
        return levelRepository.findByLevelName(levelName)
                .orElseGet(() -> levelRepository.save(Level.builder().levelName(levelName).build()));
    }

    private String classifyLevel(BigDecimal score) {
        if (score.compareTo(BigDecimal.valueOf(80)) >= 0) {
            return "Advanced";
        } else if (score.compareTo(BigDecimal.valueOf(50)) >= 0) {
            return "Intermediate";
        }
        return "Beginner";
    }

    private void validateFile(MultipartFile file) {
        com.careercompass.util.FileValidationUtils.validatePdf(file, MAX_FILE_SIZE_BYTES); // NFR-PERF-07, FR-JS-10
    }
}
