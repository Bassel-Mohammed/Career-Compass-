package com.careercompass.integration.ai;

import com.careercompass.integration.dto.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/**
 * Stub implementation of {@link DataAnalysisClient} returning realistic-shaped fake data.
 * Active by default (`careercompass.ai-service.use-mock=true`), which is what lets every other
 * Java service and controller be built, run and tested without the Python service running.
 *
 * <p>Deliberately deterministic rather than random, so demos and manual testing behave
 * predictably instead of showing different numbers for the same input.
 *
 * <p>It mirrors the <em>shape</em> of the real contract — canonical skill ids, title-case
 * classifications, four quiz options — so that switching {@code use-mock} does not change what
 * the calling code has to handle. What it cannot mirror is the substance: it never reads the PDF,
 * never consults the real taxonomy or catalog, and its scores mean nothing. Mock output must
 * never be presented as an AI result.
 */
@Component
@ConditionalOnProperty(
        prefix = "careercompass.ai-service",
        name = "use-mock",
        havingValue = "true",
        matchIfMissing = true)
public class MockDataAnalysisClient implements DataAnalysisClient {

    @Override
    public TranscriptExtractionResponse extractTranscript(TranscriptExtractionRequest request) {
        // Pretend we parsed a small, realistic transcript. Real extraction happens entirely on
        // the Python side; this never actually reads the PDF bytes.
        List<TranscriptExtractionResponse.ExtractedCourseDto> courses = List.of(
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS101").courseName("Introduction to Programming")
                        .grade("A").lowConfidence(false).warnings(List.of()).build(),
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS201").courseName("Data Structures")
                        .grade("A-").lowConfidence(false).warnings(List.of()).build(),
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS310").courseName("Operating Systems")
                        .grade("B-").lowConfidence(true)
                        .warnings(List.of("[MOCK] Grade column was ambiguous on this row."))
                        .build()
        );
        return TranscriptExtractionResponse.builder().courses(courses).build();
    }

    @Override
    public SkillVectorResponse buildSkillVector(BuildSkillVectorRequest request) {
        List<SkillScoreDto> skills = new ArrayList<>();
        for (CourseGradeDto course : nullSafe(request.getCourses())) {
            String skillId = mockSkillId(course);
            BigDecimal score = gradeToScore(course.getGrade());

            // Honour supplied quiz evidence the way the real service does: a graded quiz
            // replaces the grade-inferred score for that skill (FR-JS-20/21).
            if (request.getQuizScores() != null && request.getQuizScores().containsKey(skillId)) {
                score = request.getQuizScores().get(skillId);
            }

            skills.add(SkillScoreDto.builder()
                    .skillId(skillId)
                    .skillName(deriveSkillNameFromCourse(course.getCourseName()))
                    .score(score)
                    .build());
        }
        return SkillVectorResponse.builder()
                .taxonomyVersion("mock-v1")
                .skills(skills)
                .build();
    }

    @Override
    public SkillGapAnalysisResponse analyzeSkillGap(SkillGapAnalysisRequest request) {
        SkillVectorResponse vector = buildSkillVector(BuildSkillVectorRequest.builder()
                .courses(request.getCourses())
                .quizScores(request.getQuizScores())
                .build());

        List<SkillGapAnalysisResponse.SkillGapItemDto> gaps = vector.getSkills().stream()
                .map(skill -> {
                    BigDecimal target = BigDecimal.valueOf(75);
                    String classification = classify(skill.getScore(), target);
                    return SkillGapAnalysisResponse.SkillGapItemDto.builder()
                            .skillId(skill.getSkillId())
                            .skillName(skill.getSkillName())
                            .currentScore(skill.getScore())
                            .targetScore(target)
                            .classification(classification)
                            .explanation("[MOCK] Estimated from related coursework; "
                                    + classification.toLowerCase(Locale.ROOT) + " relative to the target level.")
                            .priority(BigDecimal.ZERO)
                            .build();
                })
                .toList();

        int overallReadiness = gaps.isEmpty() ? 0 : (int) gaps.stream()
                .mapToInt(g -> g.getCurrentScore().intValue())
                .average()
                .orElse(0);

        return SkillGapAnalysisResponse.builder()
                .skillGaps(gaps)
                .overallReadinessPercent(overallReadiness)
                .narrative(request.isIncludeNarrative()
                        ? "[MOCK] A generated summary would appear here."
                        : null)
                .build();
    }

    @Override
    public List<RecommendedCourseDto> recommendCourses(CourseRecommendationRequest request) {
        SkillGapAnalysisResponse gap = analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName(request.getCareerPathName())
                .courses(request.getCourses())
                .quizScores(request.getQuizScores())
                .build());

        int limit = request.getLimit() == null || request.getLimit() <= 0 ? 10 : request.getLimit();

        return gap.getSkillGaps().stream()
                .filter(g -> "Weak".equalsIgnoreCase(g.getClassification()))
                .limit(limit)
                .map(g -> RecommendedCourseDto.builder()
                        .courseName("[MOCK] Intro to " + g.getSkillName())
                        .sourceLink("https://example.com/courses/mock-" + slug(g.getSkillName()))
                        .platform("mock")
                        .targetedSkillId(g.getSkillId())
                        .targetedSkillName(g.getSkillName())
                        .explanation("[MOCK] Directly targets your gap in " + g.getSkillName() + ".")
                        .relevancePercent(BigDecimal.valueOf(80).setScale(2, RoundingMode.HALF_UP))
                        .build())
                .toList();
    }

    @Override
    public QuizGenerationResponse generateQuiz(QuizGenerationRequest request) {
        String skillId = request.getSkillId() == null ? "mock:general" : request.getSkillId();
        List<QuizGenerationResponse.GeneratedQuizQuestionDto> questions = new ArrayList<>();
        for (int i = 1; i <= Math.max(request.getQuestionCount(), 1); i++) {
            questions.add(QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                    .questionText("[MOCK] Sample question " + i + " about " + skillId + "?")
                    .optionA("Option A")
                    .optionB("Option B")
                    .optionC("Option C")
                    .optionD("Option D")
                    .correctOption("A")
                    .explanation("[MOCK] Option A is correct.")
                    .build());
        }
        return QuizGenerationResponse.builder()
                .skillId(skillId)
                .skillLabel(skillId)
                .questions(questions)
                .build();
    }

    @Override
    public JobMatchResponse scoreJobMatch(JobMatchRequest request) {
        // Job matching is descoped from the AI contract for this release, so this mock is the
        // only implementation. It is a placeholder heuristic, not a match score.
        double avgScore = nullSafe(request.getSkillVector()).stream()
                .mapToDouble(s -> s.getScore().doubleValue())
                .average()
                .orElse(50.0);

        int nudge = request.getJobTitle() == null ? 0 : (request.getJobTitle().length() % 10);
        BigDecimal matchScore = BigDecimal.valueOf(Math.min(100, Math.max(0, avgScore - nudge)));

        return JobMatchResponse.builder()
                .matchScore(matchScore)
                .explanation("[MOCK] Score derived from average skill level, adjusted for role fit.")
                .build();
    }

    @Override
    public SyllabusExtractionResponse submitSyllabusExtraction(SyllabusExtractionRequest request) {
        if (request == null || request.getFileContent() == null || request.getFileContent().length == 0) {
            throw new IllegalArgumentException("Syllabus file content is required.");
        }
        String extractionId = "mock-extraction-" + UUID.randomUUID();
        List<SyllabusExtractionResponse.ExtractedSkill> skills = List.of(
                mockExtractedSkill("Object-oriented programming", "mock:oop",
                        "Object-oriented programming", "intermediate", 1.0),
                mockExtractedSkill("Unit testing", "mock:unit-testing",
                        "Unit testing", "beginner", 0.8));

        return SyllabusExtractionResponse.builder()
                .extractionId(extractionId)
                .status("succeeded")
                .courseCode("MOCK101")
                .contentSha256("mock-content-sha256")
                .progress(SyllabusExtractionResponse.Progress.builder()
                        .stage("done").termsTotal(skills.size()).termsResolved(skills.size())
                        .elapsedSeconds(BigDecimal.ZERO).build())
                .result(SyllabusExtractionResponse.Result.builder()
                        .courseCode("MOCK101")
                        .totalSkills(skills.size())
                        .taxonomyVersion("mock-v1")
                        .skills(skills)
                        .build())
                .warnings(List.of("[MOCK] Skills were generated without parsing the uploaded PDF."))
                .build();
    }

    @Override
    public SyllabusExtractionResponse getSyllabusExtraction(String extractionId) {
        // Mock submissions complete synchronously; return the same deterministic proposal.
        SyllabusExtractionResponse response = submitSyllabusExtraction(
                SyllabusExtractionRequest.builder().fileContent(new byte[]{1}).build());
        return SyllabusExtractionResponse.builder()
                .extractionId(extractionId)
                .status(response.getStatus())
                .courseCode(response.getCourseCode())
                .contentSha256(response.getContentSha256())
                .progress(response.getProgress())
                .result(response.getResult())
                .warnings(response.getWarnings())
                .build();
    }

    @Override
    public SyllabusExtractionResponse cancelSyllabusExtraction(String extractionId) {
        return SyllabusExtractionResponse.builder()
                .extractionId(extractionId)
                .status("cancelled")
                .progress(SyllabusExtractionResponse.Progress.builder().stage("done").build())
                .warnings(List.of())
                .build();
    }

    @Override
    public List<TaxonomySkillSuggestion> searchTaxonomySkills(String query, int limit) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        List<TaxonomySkillSuggestion> catalog = List.of(
                TaxonomySkillSuggestion.builder().skillId("mock:oop")
                        .label("Object-oriented programming").skillType("skill")
                        .source("mock").taxonomyVersion("mock-v1").build(),
                TaxonomySkillSuggestion.builder().skillId("mock:unit-testing")
                        .label("Unit testing").skillType("skill")
                        .source("mock").taxonomyVersion("mock-v1").build(),
                TaxonomySkillSuggestion.builder().skillId("mock:docker")
                        .label("Docker").skillType("tool")
                        .source("mock").taxonomyVersion("mock-v1").build());
        String needle = query.trim().toLowerCase(Locale.ROOT);
        return catalog.stream()
                .filter(item -> item.getLabel().toLowerCase(Locale.ROOT).contains(needle)
                        || item.getSkillId().toLowerCase(Locale.ROOT).contains(needle))
                .limit(Math.max(1, limit))
                .toList();
    }

    @Override
    public PublishCourseMapResponse publishCourseMap(PublishCourseMapRequest request) {
        return PublishCourseMapResponse.builder()
                .courseMapVersion(request.getCourseMapVersion())
                .courseKey(String.join("|", request.getInstitutionCode(),
                        request.getCatalogVersion(), request.getCourseCode()))
                .courseCode(request.getCourseCode())
                .taxonomyVersion(request.getTaxonomyVersion())
                .totalSkills(request.getSkills() == null ? 0 : request.getSkills().size())
                .contentSha256("mock-published-sha256")
                .publishedAt(java.time.OffsetDateTime.now().toString())
                .idempotent(false)
                .build();
    }

    private SyllabusExtractionResponse.ExtractedSkill mockExtractedSkill(
            String term, String skillId, String label, String level, double weight) {
        return SyllabusExtractionResponse.ExtractedSkill.builder()
                .term(term)
                .canonical(SyllabusExtractionResponse.CanonicalSkill.builder()
                        .id(skillId).label(label).taxonomy("mock").build())
                .level(level)
                .weight(BigDecimal.valueOf(weight))
                .evidenceCount(1)
                .sources(List.of("clo"))
                .evidence(List.of(Map.of("source", "clo", "text", "[MOCK] " + term)))
                .match(SyllabusExtractionResponse.Match.builder()
                        .originalTerm(term)
                        .canonicalId(skillId)
                        .canonicalLabel(label)
                        .taxonomy("mock")
                        .taxonomyVersion("mock-v1")
                        .matchMethod("mock")
                        .matchScore(BigDecimal.ONE)
                        .reviewStatus("accepted")
                        .reason("[MOCK] deterministic proposal")
                        .candidates(List.of())
                        .build())
                .build();
    }

    /**
     * A stable fake canonical id. Derived from the course code where present so that the same
     * course always yields the same id across calls — the quiz write-back joins on this.
     */
    private String mockSkillId(CourseGradeDto course) {
        String basis = course.getCourseCode() != null && !course.getCourseCode().isBlank()
                ? course.getCourseCode()
                : String.valueOf(course.getCourseName());
        return "mock:" + slug(basis);
    }

    private String deriveSkillNameFromCourse(String courseName) {
        return courseName == null ? "General Skill" : courseName.trim();
    }

    private static String slug(String value) {
        return value == null ? "unknown"
                : value.trim().toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", "-");
    }

    private static <T> List<T> nullSafe(List<T> list) {
        return list == null ? List.of() : list;
    }

    private BigDecimal gradeToScore(String grade) {
        if (grade == null) {
            return BigDecimal.valueOf(50);
        }
        return switch (grade.trim().toUpperCase(Locale.ROOT)) {
            case "A", "A+" -> BigDecimal.valueOf(95);
            case "A-" -> BigDecimal.valueOf(90);
            case "B+" -> BigDecimal.valueOf(85);
            case "B" -> BigDecimal.valueOf(80);
            case "B-" -> BigDecimal.valueOf(75);
            case "C+" -> BigDecimal.valueOf(70);
            case "C" -> BigDecimal.valueOf(65);
            case "C-" -> BigDecimal.valueOf(60);
            case "D+", "D", "D-" -> BigDecimal.valueOf(50);
            default -> BigDecimal.valueOf(40);
        };
    }

    private String classify(BigDecimal score, BigDecimal target) {
        BigDecimal ratio = score.divide(target, 4, RoundingMode.HALF_UP);
        if (ratio.compareTo(BigDecimal.valueOf(0.9)) >= 0) {
            return "Strong";
        } else if (ratio.compareTo(BigDecimal.valueOf(0.6)) >= 0) {
            return "Moderate";
        }
        return "Weak";
    }
}
