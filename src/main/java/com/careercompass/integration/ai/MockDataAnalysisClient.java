package com.careercompass.integration.ai;

import com.careercompass.integration.dto.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.List;

/**
 * Stub implementation of {@link DataAnalysisClient} returning realistic-shaped fake data.
 * Active by default (`careercompass.ai-service.use-mock=true`, set in application.yml since
 * Increment 1) — this is what lets every other Java service/controller be built, run, and
 * tested end-to-end right now, without Mohammed's Python service existing yet.
 *
 * Deliberately deterministic-ish (seeded by input where reasonable) rather than fully random,
 * so manual testing/demos behave predictably rather than showing different numbers on every
 * call for the same input.
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
        // Mock: pretend we parsed a small, realistic transcript. Real extraction (pdfplumber +
        // LLM) happens entirely on the Python side; this never actually reads the PDF bytes.
        List<TranscriptExtractionResponse.ExtractedCourseDto> courses = List.of(
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS101").courseName("Introduction to Programming")
                        .grade("A").lowConfidence(false).build(),
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS201").courseName("Data Structures")
                        .grade("A-").lowConfidence(false).build(),
                TranscriptExtractionResponse.ExtractedCourseDto.builder()
                        .courseCode("CS310").courseName("Operating Systems")
                        .grade("B-").lowConfidence(true).build()
        );
        return TranscriptExtractionResponse.builder().courses(courses).build();
    }

    @Override
    public SkillVectorResponse buildSkillVector(BuildSkillVectorRequest request) {
        List<SkillScoreDto> skills = request.getCourses().stream()
                .map(course -> SkillScoreDto.builder()
                        .skillName(deriveSkillNameFromCourse(course.getCourseName()))
                        .score(gradeToScore(course.getGrade()))
                        .build())
                .toList();

        return SkillVectorResponse.builder().skills(skills).build();
    }

    @Override
    public SkillGapAnalysisResponse analyzeSkillGap(SkillGapAnalysisRequest request) {
        List<SkillGapAnalysisResponse.SkillGapItemDto> gaps = request.getSkillVector().stream()
                .map(skill -> {
                    BigDecimal target = BigDecimal.valueOf(75);
                    String classification = classify(skill.getScore(), target);
                    return SkillGapAnalysisResponse.SkillGapItemDto.builder()
                            .skillName(skill.getSkillName())
                            .currentScore(skill.getScore())
                            .targetScore(target)
                            .classification(classification)
                            .explanation("[MOCK] Estimated from related coursework; "
                                    + classification.toLowerCase() + " relative to the target level.")
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
                .build();
    }

    @Override
    public List<RecommendedCourseDto> recommendCourses(CourseRecommendationRequest request) {
        return request.getWeakSkillNames().stream()
                .map(skillName -> RecommendedCourseDto.builder()
                        .courseName("[MOCK] Intro to " + skillName)
                        .sourceLink("https://example.com/courses/mock-" + skillName.toLowerCase().replace(" ", "-"))
                        .targetedSkillName(skillName)
                        .explanation("[MOCK] Directly targets your gap in " + skillName + ".")
                        .build())
                .toList();
    }

    @Override
    public QuizGenerationResponse generateQuiz(QuizGenerationRequest request) {
        List<QuizGenerationResponse.GeneratedQuizQuestionDto> questions = new java.util.ArrayList<>();
        for (int i = 1; i <= Math.max(request.getQuestionCount(), 1); i++) {
            questions.add(QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                    .questionText("[MOCK] Sample question " + i + " about " + request.getCourseName() + "?")
                    .optionA("Option A")
                    .optionB("Option B")
                    .optionC("Option C")
                    .optionD("Option D")
                    .correctOption("A")
                    .build());
        }
        return QuizGenerationResponse.builder().questions(questions).build();
    }

    @Override
    public JobMatchResponse scoreJobMatch(JobMatchRequest request) {
        // Simple mock heuristic: average skill score, nudged deterministically by job title length
        // so different jobs don't all return an identical score during manual testing.
        double avgScore = request.getSkillVector().stream()
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

    private String deriveSkillNameFromCourse(String courseName) {
        // Extremely naive mock mapping — real mapping happens in the actual Python service
        // against the course->skill map (Section 5.3.2 Knowledge Base).
        return courseName == null ? "General Skill" : courseName.trim();
    }

    private BigDecimal gradeToScore(String grade) {
        if (grade == null) {
            return BigDecimal.valueOf(50);
        }
        return switch (grade.trim().toUpperCase()) {
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
        BigDecimal ratio = score.divide(target, 4, java.math.RoundingMode.HALF_UP);
        if (ratio.compareTo(BigDecimal.valueOf(0.9)) >= 0) {
            return "Strong";
        } else if (ratio.compareTo(BigDecimal.valueOf(0.6)) >= 0) {
            return "Moderate";
        }
        return "Weak";
    }
}
