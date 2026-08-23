package com.careercompass.integration.ai;

import com.careercompass.integration.dto.TranscriptExtractionRequest;
import com.careercompass.integration.dto.TranscriptExtractionResponse;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * HTTP-level contract test for the first real Java/FastAPI vertical slice. The JDK server is
 * deliberately used instead of mocking WebClient so this test observes the encoded multipart
 * request that will actually be sent over the wire.
 */
class HttpDataAnalysisClientTranscriptContractTest {

    private HttpServer server;
    private String baseUrl;
    private final AtomicReference<CapturedRequest> capturedRequest = new AtomicReference<>();

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/", this::handleRequest);
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
    void extractTranscript_sendsCanonicalMultipartRequestAndMapsSnakeCaseResponse() {
        byte[] pdfBytes = "%PDF-1.4\ncontract-test".getBytes(StandardCharsets.ISO_8859_1);
        HttpDataAnalysisClient client = createClient();

        TranscriptExtractionResponse response = client.extractTranscript(
                TranscriptExtractionRequest.builder()
                        .fileContent(pdfBytes)
                        .originalFilename("academic-plan.pdf")
                        .contentType("application/pdf")
                        .build());

        CapturedRequest request = capturedRequest.get();
        assertThat(request).isNotNull();
        assertThat(request.method()).isEqualTo("POST");
        assertThat(request.path()).isEqualTo("/api/v1/transcripts/parse");
        assertThat(request.contentType()).startsWith("multipart/form-data;boundary=");
        assertThat(request.body())
                .contains("name=\"file\"")
                .contains("filename=\"academic-plan.pdf\"")
                .contains("Content-Type: application/pdf")
                .contains("%PDF-1.4")
                .contains("name=\"save\"")
                .contains("false")
                .doesNotContain("jobseeker")
                .doesNotContain("fileBase64");

        assertThat(response.getCourses()).hasSize(2);
        assertThat(response.getCourses().get(0).getCourseCode()).isEqualTo("CS201");
        assertThat(response.getCourses().get(0).getCourseName()).isEqualTo("Data Structures");
        assertThat(response.getCourses().get(0).getGrade()).isEqualTo("A");
        assertThat(response.getCourses().get(0).getConfidence()).isNull();
        assertThat(response.getCourses().get(0).isLowConfidence()).isFalse();
        assertThat(response.getCourses().get(0).getWarnings()).isEmpty();

        assertThat(response.getCourses().get(1).getCourseCode()).isEqualTo("CS310");
        assertThat(response.getCourses().get(1).getConfidence()).isEqualByComparingTo("0.62");
        assertThat(response.getCourses().get(1).isLowConfidence()).isTrue();
        assertThat(response.getCourses().get(1).getWarnings())
                .containsExactly("Grade needed manual review.");
    }

    private HttpDataAnalysisClient createClient() {
        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(baseUrl);
        properties.setTimeoutSeconds(5);
        return new HttpDataAnalysisClient(WebClient.builder().baseUrl(baseUrl).build(), properties);
    }

    private void handleRequest(HttpExchange exchange) throws IOException {
        byte[] body = exchange.getRequestBody().readAllBytes();
        capturedRequest.set(new CapturedRequest(
                exchange.getRequestMethod(),
                exchange.getRequestURI().getPath(),
                exchange.getRequestHeaders().getFirst("Content-Type"),
                new String(body, StandardCharsets.ISO_8859_1)));

        byte[] response = ("""
                {
                  "courses": [
                    {
                      "course_code": "CS201",
                      "course_name": "Data Structures",
                      "grade": "A",
                      "confidence": null,
                      "low_confidence": false,
                      "warnings": []
                    },
                    {
                      "course_code": "CS310",
                      "course_name": "Operating Systems",
                      "grade": "C",
                      "confidence": 0.62,
                      "low_confidence": true,
                      "warnings": ["Grade needed manual review."]
                    }
                  ]
                }
                """).getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(200, response.length);
        exchange.getResponseBody().write(response);
        exchange.close();
    }

    private record CapturedRequest(String method, String path, String contentType, String body) {
    }
}
