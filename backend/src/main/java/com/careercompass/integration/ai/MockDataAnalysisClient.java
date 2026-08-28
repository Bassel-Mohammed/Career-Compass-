package com.careercompass.integration.ai;

import com.careercompass.integration.dto.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
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
                        .grade("A").lowConfidence(false).warnings(java.util.Collections.emptyList()).build(),
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS201").courseName("Data Structures")
                        .grade("A-").lowConfidence(false).warnings(java.util.Collections.emptyList()).build(),
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

        List<SkillGapAnalysisResponse.SkillGapItemDto> gaps = new ArrayList<>();
        List<SkillScoreDto> held = vector.getSkills();
        List<CourseGradeDto> sourceCourses = nullSafe(request.getCourses());
        for (int index = 0; index < held.size(); index++) {
            SkillScoreDto skill = held.get(index);
            CourseGradeDto sourceCourse = index < sourceCourses.size() ? sourceCourses.get(index) : null;
            BigDecimal target = BigDecimal.valueOf(75);
            String classification = classify(skill.getScore(), target);
            // Demand descends across the list so all three bands appear. The dashboard groups by
            // band and would look broken against a mock that only ever produced one of them.
            BigDecimal importance = mockImportance(index, held.size());
            gaps.add(SkillGapAnalysisResponse.SkillGapItemDto.builder()
                    .skillId(skill.getSkillId())
                    .skillName(skill.getSkillName())
                    .currentScore(skill.getScore())
                    .targetScore(target)
                    .classification(classification)
                    .explanation("[MOCK] Estimated from related coursework; "
                            + classification.toLowerCase(Locale.ROOT) + " relative to the target level.")
                    .importancePercent(importance)
                    .demandBand(mockBand(importance))
                    .postingCount(importance
                            .multiply(BigDecimal.valueOf(MOCK_SAMPLE_SIZE))
                            .divide(BigDecimal.valueOf(100), 0, RoundingMode.HALF_UP)
                            .intValue())
                    .requiredLevel("advanced")
                    .skillType("knowledge")
                    .priority(BigDecimal.ZERO)
                    .evidenceSource(request.getQuizScores() != null
                            && request.getQuizScores().containsKey(skill.getSkillId())
                            ? "grades+quizzes" : "grades")
                    .sourceCourses(sourceCourse == null ? List.of() : List.of(
                            SkillGapAnalysisResponse.CourseEvidenceDto.builder()
                                    .courseCode(sourceCourse.getCourseCode())
                                    .courseName(sourceCourse.getCourseName())
                                    .grade(sourceCourse.getGrade())
                                    .level("advanced")
                                    .build()))
                    .build());
        }

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
                .bandSummary(mockBandSummary(gaps))
                .sampleSize(MOCK_SAMPLE_SIZE)
                .coursesCounted(request.getCourses() == null ? 0 : request.getCourses().size())
                .syntheticCounted(0)
                .coursesSkipped(java.util.Collections.emptyList())
                .build();
    }

    @Override
    public CareerPathSkillsResponse getCareerPathSkills(String careerPathName) {
        List<CareerPathSkillsResponse.CareerPathSkillDto> skills = new ArrayList<>();
        for (int index = 0; index < MOCK_MARKET_SKILLS.size(); index++) {
            String label = MOCK_MARKET_SKILLS.get(index);
            BigDecimal coverage = mockImportance(index, MOCK_MARKET_SKILLS.size());
            skills.add(CareerPathSkillsResponse.CareerPathSkillDto.builder()
                    .skillId("mock:" + slug(label))
                    .label(label)
                    .skillType("knowledge")
                    .postingCount(coverage
                            .multiply(BigDecimal.valueOf(MOCK_SAMPLE_SIZE))
                            .divide(BigDecimal.valueOf(100), 0, RoundingMode.HALF_UP)
                            .intValue())
                    .coveragePercent(coverage)
                    .demandBand(mockBand(coverage))
                    .requiredLevel("advanced")
                    .sampleTerms(List.of("[MOCK] " + label))
                    .build());
        }

        Map<String, Integer> bandTotals = new LinkedHashMap<>();
        for (CareerPathSkillsResponse.CareerPathSkillDto skill : skills) {
            bandTotals.merge(skill.getDemandBand(), 1, Integer::sum);
        }

        return CareerPathSkillsResponse.builder()
                .careerPath(careerPathName)
                .sampleSize(MOCK_SAMPLE_SIZE)
                .derivedFrom("job_postings")
                .capturedAt("2026-08-07T22:51:27Z")
                .taxonomyVersion("mock-1.0")
                .total(skills.size())
                .bandTotals(bandTotals)
                .skills(skills)
                .build();
    }

    /** Postings behind the mock market, so its counts read like the real ones. */
    private static final int MOCK_SAMPLE_SIZE = 184;

    private static final List<String> MOCK_MARKET_SKILLS = List.of(
            "back-end development", "Python", "REST API development", "Docker",
            "SQL", "CI/CD pipelines", "Kubernetes", "message queues");

    /**
     * Demand spread evenly from 40% down to 3% across a list, so a mock profile always spans all
     * three bands. Not meant to resemble any real career path — only to exercise the grouping.
     */
    private static BigDecimal mockImportance(int index, int total) {
        if (total <= 1) {
            return BigDecimal.valueOf(40).setScale(2, RoundingMode.HALF_UP);
        }
        double fraction = 40.0 - (37.0 * index / (total - 1));
        return BigDecimal.valueOf(fraction).setScale(2, RoundingMode.HALF_UP);
    }

    /**
     * The AI service's bands, restated here only because the mock has no service to ask.
     * The real client passes {@code demand_band} straight through and never computes it.
     */
    private static String mockBand(BigDecimal importancePercent) {
        if (importancePercent.compareTo(BigDecimal.valueOf(25)) >= 0) {
            return "critical";
        }
        return importancePercent.compareTo(BigDecimal.TEN) >= 0 ? "important" : "useful";
    }

    private static Map<String, Map<String, Integer>> mockBandSummary(
            List<SkillGapAnalysisResponse.SkillGapItemDto> gaps) {
        Map<String, Map<String, Integer>> summary = new LinkedHashMap<>();
        for (String band : List.of("critical", "important", "useful")) {
            summary.put(band, new LinkedHashMap<>(Map.of(
                    "strong", 0, "moderate", 0, "weak", 0, "total", 0)));
        }
        for (SkillGapAnalysisResponse.SkillGapItemDto gap : gaps) {
            Map<String, Integer> bucket = summary.get(gap.getDemandBand());
            bucket.merge(gap.getClassification().toLowerCase(Locale.ROOT), 1, Integer::sum);
            bucket.merge("total", 1, Integer::sum);
        }
        return summary;
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
    public MentorMatchResponse matchMentors(MentorMatchRequest request) {
        if (request.getMentors() == null || request.getMentors().isEmpty()) {
            return MentorMatchResponse.builder().build();
        }
        
        List<MentorMatchResponse.MentorMatchItem> items = request.getMentors().stream()
                .limit(request.getLimit())
                .map(m -> MentorMatchResponse.MentorMatchItem.builder()
                        .mentorId(m.getMentorId())
                        .score(new java.math.BigDecimal("85.0"))
                        .signal("mock")
                        .alignedSkills(List.of(
                                MentorMatchResponse.AlignedSkill.builder()
                                        .skillId("mock:skill:1")
                                        .skillLabel("Mock Skill 1")
                                        .build()))
                        .gapsAddressed(1)
                        .yearsExperience(5)
                        .explanation("[MOCK] This mentor covers your mock gaps.")
                        .build())
                .toList();

        return MentorMatchResponse.builder()
                .careerPath(request.getCareerPathName())
                .taxonomyVersion("mock-v1")
                .total(items.size())
                .gapsConsidered(3)
                .items(items)
                .build();
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
    public SyllabusPreviewResponse previewSyllabusPdf(String filename, String contentType, byte[] content) {
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("Syllabus file content is required.");
        }
        // The mock cannot parse PDFs, so it reports no detected identity and the
        // upload form stays manual — the honest placeholder behaviour.
        return SyllabusPreviewResponse.builder()
                .contentSha256("mock-content-sha256")
                .totalTerms(0)
                .warnings(List.of("[MOCK] No PDF was parsed; course details were not detected."))
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
                .warnings(java.util.Collections.emptyList())
                .build();
    }

    @Override
    public List<TaxonomySkillSuggestion> searchTaxonomySkills(String query, int limit) {
        if (query == null || query.isBlank()) {
            return java.util.Collections.emptyList();
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
                        .candidates(java.util.Collections.emptyList())
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
        return list == null ? java.util.Collections.emptyList() : list;
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
