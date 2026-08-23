package com.careercompass.integration.ai;

import com.careercompass.exception.AiServiceException;
import com.careercompass.integration.dto.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.web.reactive.function.client.WebClient;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * The cross-runtime gate (ADR-010): the real Java client against the real FastAPI service.
 *
 * <p>Everything else in this suite proves the adapter against a fixture of what the AI service is
 * believed to return. Only this class proves the belief. It is what would have caught the
 * original defect — six Java paths that answered 404, and five payloads that answered 422 once
 * the paths were corrected — none of which any amount of mocking could reveal.
 *
 * <p>Skipped unless a base URL is supplied, so it never makes the normal build depend on a
 * running Python service:
 *
 * <pre>
 *   CC_EMBEDDING_BACKEND=lexical uv run uvicorn careercompass.api.app:app --port 8123
 *   mvn test -Dtest=HttpDataAnalysisClientLiveContractTest \
 *            -Dcc.ai.base-url=http://127.0.0.1:8123 -DfailIfNoSpecifiedTests=false
 * </pre>
 *
 * <p>The course codes below are real extracted MEU courses. If the AI service's extracted-course
 * coverage changes, the assertions stay valid — they check contract conformance, not a fixed
 * number of skills.
 */
@EnabledIfSystemProperty(named = "cc.ai.base-url", matches = ".+")
class HttpDataAnalysisClientLiveContractTest {

    private static final String CAREER_PATH = "Backend Development";

    private static final List<CourseGradeDto> REAL_COURSES = List.of(
            course("0182102", "B"),
            course("0412201", "A"),
            course("0413201", "B+"),
            course("0432405", "C"),
            course("0434402", "B"));

    // ── M2 ────────────────────────────────────────────────────────────────

    @Test
    void skillVector_realServiceAcceptsOurPayloadAndReturnsScoresInRange() {
        SkillVectorResponse response = client().buildSkillVector(BuildSkillVectorRequest.builder()
                .jobseekerId(1)
                .courses(REAL_COURSES)
                .build());

        assertThat(response.getSkills()).isNotEmpty();
        assertThat(response.getSkills()).allSatisfy(skill -> {
            // Canonical identity must survive the round trip: it is what quizzes and the
            // write-back key on.
            assertThat(skill.getSkillId()).isNotBlank();
            assertThat(skill.getSkillName()).isNotBlank();
            assertThat(skill.getScore()).isBetween(BigDecimal.ZERO, BigDecimal.valueOf(100));
        });
    }

    // ── M3 ────────────────────────────────────────────────────────────────

    @Test
    void skillGap_realServiceKnowsThisCareerPathAndClassifiesInTitleCase() {
        SkillGapAnalysisResponse response = client().analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName(CAREER_PATH)
                .courses(REAL_COURSES)
                .build());

        assertThat(response.getSkillGaps()).isNotEmpty();
        assertThat(response.getOverallReadinessPercent()).isBetween(0, 100);
        assertThat(response.getSkillGaps()).allSatisfy(gap -> {
            assertThat(gap.getSkillId()).isNotBlank();
            // The wire is lower case; FR-JS-13 is title case. If this ever regresses, course
            // recommendations silently return nothing rather than failing.
            assertThat(gap.getClassification()).isIn("Strong", "Moderate", "Weak");
            assertThat(gap.getCurrentScore()).isBetween(BigDecimal.ZERO, BigDecimal.valueOf(100));
            assertThat(gap.getTargetScore()).isBetween(BigDecimal.ZERO, BigDecimal.valueOf(100));
        });
    }

    @Test
    void skillGap_unknownCareerPathIsReportedWithTheNamesTheServiceActuallyKnows() {
        // Java career paths are administrator-created free text, so this is the realistic
        // failure: somebody types a path name the AI service has never heard of.
        assertThatThrownBy(() -> client().analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName("Definitely Not A Real Career Path")
                .courses(REAL_COURSES)
                .build()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("Backend Development");
    }

    // ── M4 ────────────────────────────────────────────────────────────────

    @Test
    void recommendations_realServiceReturnsGroundedCoursesWithWorkingLinks() {
        List<RecommendedCourseDto> recommendations = client().recommendCourses(
                CourseRecommendationRequest.builder()
                        .careerPathName(CAREER_PATH)
                        .courses(REAL_COURSES)
                        .limit(5)
                        .build());

        assertThat(recommendations).isNotEmpty();
        assertThat(recommendations).allSatisfy(course -> {
            assertThat(course.getCourseName()).isNotBlank();
            // NFR-AI-05: retrieved from a catalog, never generated — so the link is real.
            assertThat(course.getSourceLink()).startsWith("http");
            assertThat(course.getTargetedSkillId()).isNotBlank();
            assertThat(course.getRelevancePercent()).isBetween(BigDecimal.ZERO, BigDecimal.valueOf(100));
        });
    }

    // ── M5 ────────────────────────────────────────────────────────────────

    @Test
    void quiz_realServiceGeneratesAGradeableQuizForASkillTheGapIdentified() {
        // Take the skill id from the gap rather than hard-coding one: this proves the two
        // operations agree on identity, which is the whole point of a canonical id.
        String skillId = client().analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName(CAREER_PATH)
                .courses(REAL_COURSES)
                .build())
                .getSkillGaps().get(0).getSkillId();

        QuizGenerationResponse quiz = client().generateQuiz(QuizGenerationRequest.builder()
                .skillId(skillId)
                .questionCount(2)
                .build());

        assertThat(quiz.getSkillId()).isEqualTo(skillId);
        assertThat(quiz.getQuestions()).isNotEmpty();
        assertThat(quiz.getQuestions()).allSatisfy(question -> {
            assertThat(question.getQuestionText()).isNotBlank();
            assertThat(question.getOptionA()).isNotBlank();
            assertThat(question.getOptionD()).isNotBlank();
            // NFR-AI-07: exactly one correct option, expressed as the letter Java stores.
            assertThat(question.getCorrectOption()).isIn("A", "B", "C", "D");
        });
    }

    // ── Error path ────────────────────────────────────────────────────────

    @Test
    void transcriptParse_rejectsANonPdfWithAControlledErrorRatherThanCrashing() {
        assertThatThrownBy(() -> client().extractTranscript(TranscriptExtractionRequest.builder()
                .fileContent("this is not a pdf".getBytes())
                .originalFilename("notes.txt")
                .contentType("text/plain")
                .build()))
                .isInstanceOf(AiServiceException.class);
    }

    // ── Fixtures ──────────────────────────────────────────────────────────

    private static CourseGradeDto course(String code, String grade) {
        return CourseGradeDto.builder().courseCode(code).courseName("Course " + code).grade(grade).build();
    }

    private HttpDataAnalysisClient client() {
        String baseUrl = System.getProperty("cc.ai.base-url");

        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(baseUrl);
        // Generous: a cold service loads its taxonomy and course index on first use, and quiz
        // generation is a real model call.
        properties.setTimeoutSeconds(120);
        properties.getTimeouts().setTranscriptSeconds(120);
        properties.getTimeouts().setSkillVectorSeconds(120);
        properties.getTimeouts().setSkillGapSeconds(120);
        properties.getTimeouts().setRecommendationsSeconds(120);
        properties.getTimeouts().setQuizSeconds(180);

        return new HttpDataAnalysisClient(WebClient.builder().baseUrl(baseUrl).build(), properties);
    }
}
