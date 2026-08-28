package com.careercompass.integration.ai;

import com.careercompass.exception.AiServiceException;
import com.careercompass.integration.dto.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * HTTP-level contract tests for the JSON operations in
 * {@code docs/contracts/careercompass-ai-internal-v1.yaml}.
 *
 * <p>A real JDK HTTP server is used rather than a mocked {@code WebClient} so that these tests
 * observe the bytes actually sent and parse the bytes actually received. That is the whole point:
 * the failures this class exists to catch — a camelCase field the service will reject, a
 * {@code 0.82} rendered as 82%, a zero-based answer index read as one-based — are invisible to a
 * test that stubs the client interface.
 */
class HttpDataAnalysisClientContractTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private HttpServer server;
    private String baseUrl;
    private final Map<String, String> responses = new ConcurrentHashMap<>();
    private final Map<String, Integer> statuses = new ConcurrentHashMap<>();
    private final AtomicReference<String> lastBody = new AtomicReference<>();
    /** Path plus query string, so a GET's parameters can be asserted the way a POST's body is. */
    private final AtomicReference<String> lastPath = new AtomicReference<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/", this::handle);
        server.start();
        baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    // ── M2 skill vector ───────────────────────────────────────────────────

    @Test
    void buildSkillVector_sendsSnakeCaseCoursesAndConvertsProficiencyToPercent() throws Exception {
        respond("/api/v1/skill-vector", 200, """
                {
                  "taxonomy_version": "1.0",
                  "source": "grades",
                  "total_skills": 1,
                  "courses_counted": 1,
                  "courses_skipped": [],
                  "skills": [
                    {"skill_id": "custom:python", "label": "Python programming",
                     "proficiency": 0.82, "coverage": 1.0, "evidence": "grades", "quiz_score": null}
                  ]
                }
                """);

        SkillVectorResponse response = client().buildSkillVector(BuildSkillVectorRequest.builder()
                .jobseekerId(7)
                .careerPathId(3)
                .courses(List.of(CourseGradeDto.builder()
                        .courseCode("0412201").courseName("Programming 1").grade("B").build()))
                .quizScores(Map.of("custom:python", BigDecimal.valueOf(90)))
                .build());

        JsonNode sent = MAPPER.readTree(lastBody.get());
        assertThat(sent.get("courses").get(0).get("course_code").asText()).isEqualTo("0412201");
        // Java's percentage becomes the contract's fraction. Sending 90 would be clamped to a
        // perfect score by the service, so this conversion is not cosmetic.
        assertThat(sent.get("quiz_scores").get("custom:python").asDouble()).isEqualTo(0.9);
        // A database-local id means nothing to the AI service and must never be sent.
        assertThat(lastBody.get()).doesNotContain("jobseekerId").doesNotContain("careerPathId");

        assertThat(response.getSkills()).singleElement().satisfies(skill -> {
            assertThat(skill.getSkillId()).isEqualTo("custom:python");
            assertThat(skill.getSkillName()).isEqualTo("Python programming");
            assertThat(skill.getScore()).isEqualByComparingTo("82.00");
        });
    }

    @Test
    void buildSkillVector_rejectsProficiencyOutsideTheAgreedRange() {
        // 82 instead of 0.82 — a service that changed scale would otherwise be persisted as a
        // valid score and silently rewrite every dashboard.
        respond("/api/v1/skill-vector", 200, """
                {"source": "grades", "total_skills": 1, "courses_counted": 1, "skills":
                  [{"skill_id": "custom:python", "label": "Python", "proficiency": 82}]}
                """);

        assertThatThrownBy(() -> client().buildSkillVector(vectorRequest()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("0.0-1.0");
    }

    // ── M3 skill gap ──────────────────────────────────────────────────────

    @Test
    void analyzeSkillGap_sendsCareerPathByNameAndNormalisesClassificationCase() throws Exception {
        respond("/api/v1/skill-gap", 200, """
                {
                  "career_path": "Backend Development",
                  "summary": {"strong": 1, "moderate": 0, "weak": 1},
                  "total_requirements": 4,
                  "requirements_met": 1,
                  "narrative": null,
                  "skills": [
                    {"skill_id": "custom:sql", "label": "SQL", "required_proficiency": 0.85,
                     "current_level": 0.2, "gap": 0.65, "classification": "weak", "priority": 0.31},
                    {"skill_id": "custom:git", "label": "Git", "required_proficiency": 0.5,
                     "current_level": 0.9, "gap": 0.0, "classification": "strong", "priority": 0.0}
                  ]
                }
                """);

        SkillGapAnalysisResponse response = client().analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName("Backend Development")
                .courses(List.of(CourseGradeDto.builder().courseCode("0412201").grade("B").build()))
                .build());

        assertThat(MAPPER.readTree(lastBody.get()).get("career_path").asText())
                .isEqualTo("Backend Development");

        // FR-JS-13 uses title case; the wire is lower case. A mismatch here produces an empty
        // recommendation list rather than an error, so it is asserted explicitly.
        assertThat(response.getSkillGaps().get(0).getClassification()).isEqualTo("Weak");
        assertThat(response.getSkillGaps().get(1).getClassification()).isEqualTo("Strong");
        assertThat(response.getSkillGaps().get(0).getSkillId()).isEqualTo("custom:sql");
        assertThat(response.getSkillGaps().get(0).getCurrentScore()).isEqualByComparingTo("20.00");
        assertThat(response.getSkillGaps().get(0).getTargetScore()).isEqualByComparingTo("85.00");
        // Readiness is derived, not a contract field: 1 of 4 requirements met.
        assertThat(response.getOverallReadinessPercent()).isEqualTo(25);
    }

    @Test
    void analyzeSkillGap_carriesTheMarketDemandBehindEachRequirement() {
        respond("/api/v1/skill-gap", 200, """
                {
                  "career_path": "Backend Development",
                  "summary": {"strong": 0, "moderate": 0, "weak": 1},
                  "band_summary": {
                    "critical": {"strong": 0, "moderate": 0, "weak": 1, "total": 1},
                    "important": {"strong": 0, "moderate": 0, "weak": 0, "total": 0},
                    "useful": {"strong": 0, "moderate": 0, "weak": 0, "total": 0}
                  },
                  "sample_size": 184,
                  "courses_counted": 3,
                  "synthetic_counted": 2,
                  "courses_skipped": [
                    {"course_code": "0999999", "reason": "no skill map"},
                    {"course_code": "0888888", "reason": "not passed", "status": "Fail"}
                  ],
                  "total_requirements": 1,
                  "requirements_met": 0,
                  "skills": [
                    {"skill_id": "custom:back-end-development", "label": "back-end development",
                     "skill_type": "knowledge", "required_level": "advanced",
                     "required_proficiency": 0.85, "current_level": 0.0, "gap": 0.85,
                     "classification": "weak", "importance": 0.391, "demand_band": "critical",
                     "posting_count": 72, "priority": 0.3324, "evidence": "grades+quizzes",
                     "course_count": 1,
                     "courses": [{"course_code": "0412201", "course_name": "Databases",
                                   "grade": "B", "weight": 0.85, "level": "advanced"}]}
                  ]
                }
                """);

        SkillGapAnalysisResponse response = client().analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName("Backend Development")
                .courses(List.of(CourseGradeDto.builder().courseCode("0412201").grade("B").build()))
                .build());

        SkillGapAnalysisResponse.SkillGapItemDto item = response.getSkillGaps().get(0);
        // The band is passed straight through. Java must never recompute it: the thresholds live
        // beside the job-posting data that justifies them, and a second copy here would be the
        // two disagreeing about what "critical" means the first time either moved.
        assertThat(item.getDemandBand()).isEqualTo("critical");
        // 0.391 of postings, on the 0-100 scale ADR-003 fixes for this side of the wire.
        assertThat(item.getImportancePercent()).isEqualByComparingTo("39.10");
        assertThat(item.getPostingCount()).isEqualTo(72);
        assertThat(item.getRequiredLevel()).isEqualTo("advanced");
        assertThat(item.getSkillType()).isEqualTo("knowledge");
        assertThat(item.getEvidenceSource()).isEqualTo("grades+quizzes");
        assertThat(item.getSourceCourses()).singleElement().satisfies(course -> {
            assertThat(course.getCourseCode()).isEqualTo("0412201");
            assertThat(course.getCourseName()).isEqualTo("Databases");
            assertThat(course.getGrade()).isEqualTo("B");
            assertThat(course.getLevel()).isEqualTo("advanced");
        });

        // The denominator, without which 39.1% is a number a student has no reason to trust.
        assertThat(response.getSampleSize()).isEqualTo(184);
        assertThat(response.getBandSummary().get("critical")).containsEntry("total", 1);

        // "You never studied this" and "we could not read your courses" produce the same empty
        // bar and mean opposite things. Only these fields let the caller tell them apart.
        assertThat(response.getCoursesCounted()).isEqualTo(3);
        assertThat(response.getSyntheticCounted()).isEqualTo(2);
        assertThat(response.getCoursesSkipped()).hasSize(2);
        assertThat(response.getCoursesSkipped().get(0).getCourseCode()).isEqualTo("0999999");
        assertThat(response.getCoursesSkipped().get(0).getReason()).isEqualTo("no skill map");
        assertThat(response.getCoursesSkipped().get(1).getStatus()).isEqualTo("Fail");
    }

    @Test
    void getCareerPathSkills_sendsTheNameAsAQueryParamAndScalesCoverage() {
        // A query parameter, not a path segment. Two of the nine career-path names contain a
        // slash, and a slash is legal unencoded inside a query value — which is exactly why it
        // must not be a path segment, where it would split into two segments instead.
        respond("/api/v1/career-paths/skills", 200, """
                {
                  "career_path": "UI/UX Design",
                  "sample_size": 269,
                  "derived_from": "job_postings",
                  "captured_at": "2026-08-07T22:51:27.318954+00:00",
                  "total": 1,
                  "band_totals": {"critical": 8, "important": 9, "useful": 26},
                  "skills": [
                    {"skill_id": "custom:figma", "label": "Figma", "skill_type": "tool",
                     "posting_count": 110, "coverage": 0.4089, "demand_band": "critical",
                     "required_level": "advanced", "required_score": 40.9,
                     "sample_terms": ["Figma", "Figma prototypes"]}
                  ]
                }
                """);

        CareerPathSkillsResponse response = client().getCareerPathSkills("UI/UX Design");

        assertThat(lastPath.get()).startsWith("/api/v1/career-paths/skills?");
        // Spring encodes the space and leaves the slash, which is what the AI service parses
        // back to "UI/UX Design". Asserted as sent rather than as one might expect it: the
        // point of the test is that the name survives the round trip intact.
        assertThat(lastPath.get()).contains("career_path=UI/UX%20Design");

        assertThat(response.getSampleSize()).isEqualTo(269);
        assertThat(response.getBandTotals()).containsEntry("critical", 8);

        CareerPathSkillsResponse.CareerPathSkillDto skill = response.getSkills().get(0);
        assertThat(skill.getLabel()).isEqualTo("Figma");
        assertThat(skill.getDemandBand()).isEqualTo("critical");
        assertThat(skill.getPostingCount()).isEqualTo(110);
        assertThat(skill.getCoveragePercent()).isEqualByComparingTo("40.89");
        assertThat(skill.getSampleTerms()).containsExactly("Figma", "Figma prototypes");
    }

    @Test
    void analyzeSkillGap_unknownCareerPathSurfacesTheNamesTheServiceKnows() {
        respond("/api/v1/skill-gap", 404, """
                {"type": "career-path-not-found", "title": "Unknown career path", "status": 404,
                 "detail": "'Software Engineer' is not a known career path.",
                 "known": ["Backend Development", "Cybersecurity"]}
                """);

        assertThatThrownBy(() -> client().analyzeSkillGap(SkillGapAnalysisRequest.builder()
                .careerPathName("Software Engineer")
                .courses(List.of(CourseGradeDto.builder().courseCode("0412201").build()))
                .build()))
                .isInstanceOf(AiServiceException.class)
                // The administrator who named the path needs to see what it should have been.
                .hasMessageContaining("Backend Development")
                .satisfies(ex -> assertThat(((AiServiceException) ex).getStatus())
                        .isEqualTo(HttpStatus.BAD_GATEWAY));
    }

    // ── M4 recommendations ────────────────────────────────────────────────

    @Test
    void recommendCourses_flattensTheNestedCourseAndKeepsTheLink() {
        respond("/api/v1/recommendations", 200, """
                {
                  "career_path": "Backend Development",
                  "total": 1,
                  "items": [
                    {"skill_id": "custom:sql", "skill_label": "SQL",
                     "course": {"course_id": "coursera:abc", "title": "Databases 101",
                                "platform": "coursera", "url": "https://example.com/db",
                                "level": "beginner", "language": "en"},
                     "relevance": 0.83, "matched_in_title": true,
                     "explanation": "Closes your SQL gap."}
                  ],
                  "skills_without_courses": [{"skill_id": "custom:kafka", "skill_label": "Kafka"}]
                }
                """);

        List<RecommendedCourseDto> recommendations = client().recommendCourses(
                CourseRecommendationRequest.builder()
                        .careerPathName("Backend Development")
                        .courses(List.of(CourseGradeDto.builder().courseCode("0412201").build()))
                        .limit(10)
                        .build());

        assertThat(recommendations).singleElement().satisfies(course -> {
            assertThat(course.getCourseName()).isEqualTo("Databases 101");
            assertThat(course.getSourceLink()).isEqualTo("https://example.com/db");
            assertThat(course.getTargetedSkillId()).isEqualTo("custom:sql");
            assertThat(course.getRelevancePercent()).isEqualByComparingTo("83.00");
        });
    }

    @Test
    void recommendCourses_rejectsACourseWithNoLink() {
        // NFR-AI-05: a recommendation the student cannot open is worse than none at all, so
        // this is a broken response rather than a row to persist.
        respond("/api/v1/recommendations", 200, """
                {"total": 1, "items": [
                  {"skill_id": "custom:sql",
                   "course": {"course_id": "x", "title": "No link", "platform": "coursera", "url": ""},
                   "relevance": 0.5, "explanation": "..."}]}
                """);

        assertThatThrownBy(() -> client().recommendCourses(CourseRecommendationRequest.builder()
                .careerPathName("Backend Development")
                .courses(List.of(CourseGradeDto.builder().courseCode("0412201").build()))
                .build()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("without a title or link");
    }

    // ── M5 quizzes ────────────────────────────────────────────────────────

    @Test
    void generateQuiz_convertsZeroBasedAnswerIndexToTheStoredLetter() throws Exception {
        respond("/api/v1/quizzes", 201, """
                {
                  "skill_id": "custom:sql", "skill_label": "SQL", "question_count": 2,
                  "questions": [
                    {"question_id": "q1", "question": "Which clause filters rows?",
                     "options": ["SELECT", "WHERE", "ORDER BY", "GROUP BY"]},
                    {"question_id": "q2", "question": "Which joins all left rows?",
                     "options": ["INNER", "CROSS", "LEFT", "SELF"]}
                  ],
                  "answer_key": {
                    "q1": {"correct_index": 1, "correct_answer": "WHERE", "explanation": "WHERE filters."},
                    "q2": {"correct_index": 2, "correct_answer": "LEFT", "explanation": "LEFT keeps all left rows."}
                  },
                  "warnings": []
                }
                """);

        QuizGenerationResponse response = client().generateQuiz(QuizGenerationRequest.builder()
                .skillId("custom:sql").questionCount(2).build());

        assertThat(MAPPER.readTree(lastBody.get()).get("skill_id").asText()).isEqualTo("custom:sql");

        // index 1 is B and index 2 is C. An off-by-one here would mis-grade every attempt ever
        // taken, so both the letter and the option text it points at are asserted.
        assertThat(response.getQuestions()).hasSize(2);
        assertThat(response.getQuestions().get(0).getCorrectOption()).isEqualTo("B");
        assertThat(response.getQuestions().get(0).getOptionB()).isEqualTo("WHERE");
        assertThat(response.getQuestions().get(1).getCorrectOption()).isEqualTo("C");
        assertThat(response.getQuestions().get(1).getOptionC()).isEqualTo("LEFT");
    }

    @Test
    void generateQuiz_dropsQuestionsWhoseAnswerCannotBeResolved() {
        respond("/api/v1/quizzes", 201, """
                {
                  "skill_id": "custom:sql", "question_count": 3,
                  "questions": [
                    {"question_id": "q1", "question": "Good", "options": ["a", "b", "c", "d"]},
                    {"question_id": "q2", "question": "Index out of range", "options": ["a", "b", "c", "d"]},
                    {"question_id": "q3", "question": "Only three options", "options": ["a", "b", "c"]}
                  ],
                  "answer_key": {
                    "q1": {"correct_index": 0, "correct_answer": "a"},
                    "q2": {"correct_index": 9, "correct_answer": "?"},
                    "q3": {"correct_index": 0, "correct_answer": "a"}
                  }
                }
                """);

        QuizGenerationResponse response = client().generateQuiz(QuizGenerationRequest.builder()
                .skillId("custom:sql").questionCount(3).build());

        // Storing an ungradeable question would mark students wrong forever; dropping it is the
        // only safe option, and it must not take the well-formed questions down with it.
        assertThat(response.getQuestions()).singleElement()
                .satisfies(q -> assertThat(q.getQuestionText()).isEqualTo("Good"));
    }

    // ── Descoped capability ───────────────────────────────────────────────

    @Test
    void scoreJobMatch_failsAsOutOfScopeRatherThanCallingAMissingPath() {
        assertThatThrownBy(() -> client().scoreJobMatch(JobMatchRequest.builder()
                .jobTitle("Backend Engineer").build()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("not part of the current release");
    }

    // ── Transport failures ────────────────────────────────────────────────

    @Test
    void unavailableDependencyIsReportedAsUnavailableRatherThanAsAServerError() {
        respond("/api/v1/recommendations", 503, """
                {"type": "catalog-unavailable", "title": "No catalog", "status": 503,
                 "detail": "No course catalog has been built."}
                """);

        assertThatThrownBy(() -> client().recommendCourses(CourseRecommendationRequest.builder()
                .careerPathName("Backend Development")
                .courses(List.of(CourseGradeDto.builder().courseCode("0412201").build()))
                .build()))
                .isInstanceOf(AiServiceException.class)
                .satisfies(ex -> assertThat(((AiServiceException) ex).getStatus())
                        .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE));
    }

    @Test
    void coursesWithoutACodeCannotBeJoinedAndAreReportedClearly() {
        // course_code is the deterministic join key. Silently sending nothing would come back
        // as an empty skill profile, which reads to a student as "you have no skills".
        assertThatThrownBy(() -> client().buildSkillVector(BuildSkillVectorRequest.builder()
                .courses(List.of(CourseGradeDto.builder().courseName("Programming 1").grade("B").build()))
                .build()))
                .isInstanceOf(AiServiceException.class)
                .hasMessageContaining("course code");
    }

    // ── Fixtures ──────────────────────────────────────────────────────────

    private BuildSkillVectorRequest vectorRequest() {
        return BuildSkillVectorRequest.builder()
                .courses(List.of(CourseGradeDto.builder().courseCode("0412201").grade("B").build()))
                .build();
    }

    private void respond(String path, int status, String json) {
        responses.put(path, json);
        statuses.put(path, status);
    }

    private HttpDataAnalysisClient client() {
        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(baseUrl);
        properties.setTimeoutSeconds(5);
        return new HttpDataAnalysisClient(WebClient.builder().baseUrl(baseUrl).build(), properties);
    }

    private void handle(HttpExchange exchange) throws IOException {
        lastBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));

        String query = exchange.getRequestURI().getRawQuery();
        lastPath.set(exchange.getRequestURI().getRawPath() + (query == null ? "" : "?" + query));

        String path = exchange.getRequestURI().getPath();
        String json = responses.getOrDefault(path, "{}");
        int status = statuses.getOrDefault(path, 200);

        byte[] payload = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type",
                status >= 400 ? "application/problem+json" : "application/json");
        exchange.sendResponseHeaders(status, payload.length);
        exchange.getResponseBody().write(payload);
        exchange.close();
    }
}
