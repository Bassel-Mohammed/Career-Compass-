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
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

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
 * <p><b>Quiz write-back (FR-JS-20/21/22):</b> {@code recomputeAndPersistSkillDashboard} collects
 * the latest completed {@link Quiz} per canonical {@code skillId} and sends those scores to the
 * AI service as quiz evidence; the AI service recomputes the vector with them folded in, and
 * skills with no quiz keep their grade-based score (FR-JS-22).
 *
 * <p>This replaces an earlier simplification in which a quiz was matched to a skill by comparing
 * its course name to the skill's name. That only held while one course mapped to exactly one
 * identically-named skill. Against a real ontology — many courses to one skill, one course to
 * many skills — it matched nothing, so quiz results silently stopped affecting the dashboard.
 * Evidence now travels with an explicit skill id, and a quiz that has none is skipped rather
 * than attributed to a guess.
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

        byte[] fileContent;
        try {
            fileContent = file.getBytes();
        } catch (java.io.IOException e) {
            throw new IllegalStateException("Could not read the uploaded file.", e);
        }

        TranscriptExtractionRequest request = TranscriptExtractionRequest.builder()
                .fileContent(fileContent)
                .originalFilename(file.getOriginalFilename())
                .contentType(file.getContentType())
                .build();

        TranscriptExtractionResponse extraction = dataAnalysisClient.extractTranscript(request);

        List<TranscriptReviewResponse.ExtractedCourseItem> items = extraction.getCourses().stream()
                .map(c -> TranscriptReviewResponse.ExtractedCourseItem.builder()
                        .courseCode(c.getCourseCode())
                        .courseName(c.getCourseName())
                        .grade(c.getGrade())
                        .confidence(c.getConfidence())
                        .lowConfidence(c.isLowConfidence())
                        .warnings(c.getWarnings())
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
                        .courseCode(c.getCourseCode())
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
                    item.setCourseCode(r.getCourseCode());
                    item.setCourseName(r.getCourseName());
                    item.setGrade(r.getGrade());
                    return item;
                })
                .toList();

        return recomputeAndPersistSkillDashboard(jobSeeker, courseItems);
    }

    private SkillDashboardResponse recomputeAndPersistSkillDashboard(
            JobSeeker jobSeeker, List<ConfirmTranscriptRequest.CourseGradeItem> courses) {

        List<CourseGradeDto> courseGrades = courses.stream()
                .map(c -> CourseGradeDto.builder()
                        .courseCode(c.getCourseCode())
                        .courseName(c.getCourseName())
                        .grade(c.getGrade())
                        .build())
                .toList();

        // FR-JS-20: graded quiz evidence, keyed by canonical skill id — the "red dashed loop"
        // in Figure 5.3.1.1. Sent to the AI service rather than patched into the returned vector
        // locally, so the vector the dashboard shows and the vector the gap was built from
        // cannot disagree.
        Map<String, BigDecimal> quizScores = latestQuizScoresBySkillId(jobSeeker.getJobseekerId());
        String careerPathName = jobSeeker.getCareerPath().getTitle();

        // Module 2: the skill vector, with quiz evidence already folded in where it exists.
        SkillVectorResponse skillVector = dataAnalysisClient.buildSkillVector(
                BuildSkillVectorRequest.builder()
                        .jobseekerId(jobSeeker.getJobseekerId())
                        .careerPathId(jobSeeker.getCareerPath().getCareerPathId())
                        .courses(courseGrades)
                        .quizScores(quizScores)
                        .build());

        // Python's current v1 response exposes taxonomy_version but not a durable vector id.
        // Java therefore issues an opaque projection version for this persisted refresh. It is
        // intentionally not derived from labels or scores and can later become the FK/reference
        // to an immutable vector document without changing existing rows.
        String vectorVersion = UUID.randomUUID().toString();
        String taxonomyVersion = skillVector.getTaxonomyVersion();

        // Upsert every skill in the new vector, then remove only the rows it no longer
        // contains. Deleting the whole set first and re-inserting looks simpler but is not
        // equivalent: the removed rows stay in the persistence context until the transaction
        // ends, and re-saving the same composite ids inside the same transaction cancels the
        // inserts, leaving the job seeker with no skills at all.
        Set<Integer> currentSkillIds = new HashSet<>();
        for (SkillScoreDto skillScore : skillVector.getSkills()) {
            currentSkillIds.add(persistJobseekerSkill(
                    jobSeeker, skillScore, vectorVersion, taxonomyVersion));
        }
        removeSkillsNoLongerInVector(jobSeeker.getJobseekerId(), currentSkillIds);

        // Module 3: skill-gap analysis against the same courses and the same quiz evidence.
        SkillGapAnalysisResponse gapResponse = dataAnalysisClient.analyzeSkillGap(
                SkillGapAnalysisRequest.builder()
                        .careerPathName(careerPathName)
                        .courses(courseGrades)
                        .quizScores(quizScores)
                        .build());

        List<SkillLevelResponse> skillLevels = gapResponse.getSkillGaps().stream()
                .sorted(Comparator.comparing(SkillGapAnalysisResponse.SkillGapItemDto::getCurrentScore)) // weakest-first, matches Figure 5.4.6
                .map(gap -> SkillLevelResponse.builder()
                        .canonicalSkillId(gap.getSkillId())
                        .skillName(gap.getSkillName())
                        .score(gap.getCurrentScore())
                        .classification(gap.getClassification())
                        .explanation(gap.getExplanation())
                        .build())
                .toList();

        return SkillDashboardResponse.builder()
                .jobseekerId(jobSeeker.getJobseekerId())
                .careerPathTitle(jobSeeker.getCareerPath().getTitle())
                .vectorVersion(vectorVersion)
                .taxonomyVersion(taxonomyVersion)
                .overallReadinessPercent(gapResponse.getOverallReadinessPercent())
                .skills(skillLevels)
                .basedOnQuizResults(!quizScores.isEmpty()) // FR-JS-20/21 vs FR-JS-22 fallback
                .build();
    }

    /**
     * The most recent completed quiz score per canonical skill id.
     *
     * <p>Fetched in one query and grouped in memory: a vector routinely holds 70+ skills, and a
     * query per skill would be 70 round trips on every dashboard load.
     *
     * <p>Quizzes predating the {@code skillId} column are skipped rather than guessed at —
     * without an id there is no sound way to say which skill a quiz assessed, and attributing it
     * to the wrong one would silently corrupt the vector.
     */
    public Map<String, BigDecimal> latestQuizScoresBySkillId(Integer jobseekerId) {
        Map<String, BigDecimal> scores = new LinkedHashMap<>();
        for (Quiz quiz : quizRepository
                .findByJobSeeker_JobseekerIdAndTakenAtIsNotNullOrderByTakenAtDesc(jobseekerId)) {
            if (quiz.getSkillId() == null || quiz.getSkillId().isBlank() || quiz.getScore() == null) {
                continue;
            }
            // Ordered most-recent-first, so the first entry seen per skill is the latest.
            scores.putIfAbsent(quiz.getSkillId(), quiz.getScore());
        }
        return scores;
    }

    /**
     * Removes stored skills the freshly computed vector no longer contains — what a re-upload
     * or a career-path change leaves behind. Without this, a skill dropped from the vector
     * would keep showing yesterday's score on the dashboard forever.
     */
    private void removeSkillsNoLongerInVector(Integer jobseekerId, Set<Integer> currentSkillIds) {
        List<JobseekerSkill> stale = jobseekerSkillRepository.findByJobSeeker_JobseekerId(jobseekerId)
                .stream()
                .filter(existing -> !currentSkillIds.contains(existing.getId().getSkillId()))
                .toList();
        if (!stale.isEmpty()) {
            jobseekerSkillRepository.deleteAll(stale);
        }
    }

    /** @return the local skill id that was written, so the caller can identify stale rows. */
    private Integer persistJobseekerSkill(JobSeeker jobSeeker, SkillScoreDto skillScore,
                                          String vectorVersion, String taxonomyVersion) {
        validatePercentage(skillScore.getScore(), "skill score");
        Skill skill = getOrCreateSkill(skillScore, taxonomyVersion);
        Level level = getOrCreateLevel(classifyLevel(skillScore.getScore()));

        JobseekerSkillId id = new JobseekerSkillId(jobSeeker.getJobseekerId(), skill.getSkillId());

        JobseekerSkill jobseekerSkill = jobseekerSkillRepository.findById(id)
                .orElse(JobseekerSkill.builder().id(id).jobSeeker(jobSeeker).skill(skill).build());

        jobseekerSkill.setLevel(level);
        jobseekerSkill.setScore(skillScore.getScore());
        jobseekerSkill.setVectorVersion(vectorVersion);
        jobseekerSkill.setTaxonomyVersion(taxonomyVersion);

        jobseekerSkillRepository.save(jobseekerSkill);
        return skill.getSkillId();
    }

    private Skill getOrCreateSkill(SkillScoreDto skillScore, String taxonomyVersion) {
        String canonicalSkillId = normalizeIdentity(skillScore.getSkillId());
        String skillName = skillScore.getSkillName();

        if (canonicalSkillId == null) {
            // Legacy/mock compatibility only. Real v1 responses always carry a canonical id.
            return skillRepository.findBySkillName(skillName)
                    .orElseGet(() -> skillRepository.save(Skill.builder().skillName(skillName).build()));
        }

        Optional<Skill> byCanonicalId = skillRepository.findByCanonicalSkillId(canonicalSkillId);
        if (byCanonicalId.isPresent()) {
            Skill existing = byCanonicalId.get();
            existing.setSkillName(skillName);
            existing.setTaxonomyVersion(taxonomyVersion);
            return skillRepository.save(existing);
        }

        // Safe lazy backfill: a legacy row may already represent this skill by its old label. It
        // can be claimed only while it has no canonical identity; never overwrite a different id.
        Optional<Skill> legacyByName = skillRepository.findBySkillName(skillName);
        if (legacyByName.isPresent()) {
            Skill legacy = legacyByName.get();
            if (legacy.getCanonicalSkillId() != null
                    && !canonicalSkillId.equals(legacy.getCanonicalSkillId())) {
                throw new IllegalStateException(
                        "Two canonical skills share the legacy label '" + skillName
                                + "'. Backfill the skills table before retrying.");
            }
            legacy.setCanonicalSkillId(canonicalSkillId);
            legacy.setTaxonomyVersion(taxonomyVersion);
            return skillRepository.save(legacy);
        }

        return skillRepository.save(Skill.builder()
                .canonicalSkillId(canonicalSkillId)
                .skillName(skillName)
                .taxonomyVersion(taxonomyVersion)
                .build());
    }

    private String normalizeIdentity(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private void validatePercentage(BigDecimal value, String field) {
        if (value == null || value.compareTo(BigDecimal.ZERO) < 0
                || value.compareTo(BigDecimal.valueOf(100)) > 0) {
            throw new IllegalStateException(field + " must be between 0 and 100.");
        }
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
