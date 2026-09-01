package com.careercompass.integration.ai;

import com.careercompass.integration.dto.PublishCourseMapRequest;
import com.careercompass.integration.dto.PublishCourseMapResponse;
import com.careercompass.integration.dto.SyllabusExtractionRequest;
import com.careercompass.integration.dto.SyllabusExtractionResponse;
import com.careercompass.integration.dto.TaxonomySkillSuggestion;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

/** Wire-level coverage for the review-first syllabus contract (M8). */
class HttpDataAnalysisClientSyllabusContractTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private HttpServer server;
    private String baseUrl;
    private final AtomicReference<CapturedRequest> captured = new AtomicReference<>();

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

    @Test
    void submitSyllabusExtraction_isMultipartProposalOnlyAndMapsAuditFields() {
        SyllabusExtractionResponse response = client().submitSyllabusExtraction(
                SyllabusExtractionRequest.builder()
                        .fileContent("%PDF-1.4\nsyllabus".getBytes(StandardCharsets.ISO_8859_1))
                        .originalFilename("cs101.pdf")
                        .contentType("application/pdf")
                        .storeResults(false)
                        .build());

        CapturedRequest request = captured.get();
        assertThat(request.method()).isEqualTo("POST");
        assertThat(request.path()).isEqualTo("/api/v1/extractions");
        assertThat(request.contentType()).startsWith("multipart/form-data;boundary=");
        assertThat(request.body())
                .contains("name=\"file\"")
                .contains("filename=\"cs101.pdf\"")
                .contains("name=\"store\"")
                .contains("false");

        assertThat(response.getStatus()).isEqualTo("succeeded");
        assertThat(response.getResult().getSkills()).singleElement().satisfies(skill -> {
            assertThat(skill.getTerm()).isEqualTo("Unit testing");
            assertThat(skill.getMatch().getCanonicalId()).isEqualTo("custom:unit-testing");
            assertThat(skill.getMatch().getMatchScore()).isEqualByComparingTo("0.83");
            assertThat(skill.getEvidence()).hasSize(1);
            assertThat(skill.getEvidence().get(0)).containsEntry("source", "clo");
        });
    }

    @Test
    void searchTaxonomySkills_usesQueryAndMapsCanonicalIdentity() {
        List<TaxonomySkillSuggestion> results = client().searchTaxonomySkills("unit test", 7);

        assertThat(captured.get().path()).isEqualTo("/api/v1/taxonomy/skills");
        assertThat(captured.get().query()).contains("q=unit%20test").contains("limit=7");
        assertThat(results).singleElement().satisfies(skill -> {
            assertThat(skill.getSkillId()).isEqualTo("custom:unit-testing");
            assertThat(skill.getLabel()).isEqualTo("Unit testing");
            assertThat(skill.getTaxonomyVersion()).isEqualTo("1.0");
        });
    }

    @Test
    void publishCourseMap_sendsCompleteSnakeCaseReplacementAndMapsConfirmation() throws Exception {
        PublishCourseMapResponse response = client().publishCourseMap(
                PublishCourseMapRequest.builder()
                        .courseMapVersion("map:abc")
                        .institutionCode("university:1")
                        .catalogVersion("2026")
                        .courseCode("CS101")
                        .sourceOutcomeId("learning-outcome:9")
                        .taxonomyVersion("1.0")
                        .skills(List.of(PublishCourseMapRequest.ApprovedSkill.builder()
                                .skillId("custom:unit-testing")
                                .skillLabel("Unit testing")
                                .term("Unit testing")
                                .level("intermediate")
                                .weight(BigDecimal.valueOf(0.8))
                                .evidenceCount(1)
                                .sources(List.of("clo"))
                                .evidence(List.of(Map.of("source", "clo", "text", "Write tests")))
                                .build()))
                        .build());

        CapturedRequest request = captured.get();
        assertThat(request.method()).isEqualTo("PUT");
        assertThat(request.path()).isEqualTo("/api/v1/course-maps/map:abc");
        JsonNode body = MAPPER.readTree(request.body());
        assertThat(body.get("institution_code").asText()).isEqualTo("university:1");
        assertThat(body.get("catalog_version").asText()).isEqualTo("2026");
        assertThat(body.get("source_outcome_id").asText()).isEqualTo("learning-outcome:9");
        assertThat(body.get("skills").get(0).get("skill_id").asText())
                .isEqualTo("custom:unit-testing");
        assertThat(body.has("courseMapVersion")).isFalse();

        assertThat(response.getCourseMapVersion()).isEqualTo("map:abc");
        assertThat(response.getTotalSkills()).isEqualTo(1);
        assertThat(response.isIdempotent()).isFalse();
    }

    private HttpDataAnalysisClient client() {
        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(baseUrl);
        properties.setTimeoutSeconds(5);
        return new HttpDataAnalysisClient(WebClient.builder().baseUrl(baseUrl).build(), properties);
    }

    private void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        captured.set(new CapturedRequest(
                exchange.getRequestMethod(), path, exchange.getRequestURI().getRawQuery(),
                exchange.getRequestHeaders().getFirst("Content-Type"),
                new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.ISO_8859_1)));

        String json;
        int status = 200;
        if (path.equals("/api/v1/extractions")) {
            status = 202;
            json = """
                    {
                      "extraction_id":"ext-1", "status":"succeeded", "course_code":"CS101",
                      "content_sha256":"abc", "degraded":false,
                      "progress":{"stage":"done","terms_total":1,"terms_resolved":1,"elapsed_seconds":1.2},
                      "result":{"course_code":"CS101","total_skills":1,"taxonomy_version":"1.0","skills":[
                        {"term":"Unit testing","canonical":null,"level":"intermediate","weight":0.8,
                         "evidence_count":1,"sources":["clo"],
                         "evidence":[{"source":"clo","text":"Write tests"}],
                         "match":{"original_term":"Unit testing","canonical_id":"custom:unit-testing",
                           "canonical_label":"Unit testing","taxonomy":"custom","taxonomy_version":"1.0",
                           "match_method":"embedding_reranker","match_score":0.83,"review_status":"accepted",
                           "reason":"above threshold","candidates":[]}}
                      ]}, "warnings":[], "error":null,
                      "created_at":"2026-08-25T00:00:00Z","finished_at":"2026-08-25T00:00:02Z"
                    }
                    """;
        } else if (path.equals("/api/v1/taxonomy/skills")) {
            json = """
                    {"total":1,"items":[{"skill_id":"custom:unit-testing","label":"Unit testing",
                    "skill_type":"skill","source":"custom","description":"Testing one unit",
                    "taxonomy_version":"1.0"}]}
                    """;
        } else if (path.equals("/api/v1/course-maps/map:abc")) {
            json = """
                    {"course_map_version":"map:abc","course_key":"university:1|2026|CS101",
                    "course_code":"CS101","taxonomy_version":"1.0","total_skills":1,
                    "content_sha256":"published-hash","published_at":"2026-08-25T00:01:00Z",
                    "idempotent":false}
                    """;
        } else {
            status = 404;
            json = "{\"type\":\"not-found\",\"title\":\"Not found\",\"status\":404}";
        }

        byte[] response = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type",
                status >= 400 ? "application/problem+json" : "application/json");
        exchange.sendResponseHeaders(status, response.length);
        exchange.getResponseBody().write(response);
        exchange.close();
    }

    private record CapturedRequest(
            String method, String path, String query, String contentType, String body) {
    }
}
