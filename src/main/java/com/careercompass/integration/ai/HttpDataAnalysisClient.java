package com.careercompass.integration.ai;

import com.careercompass.integration.dto.*;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;
import java.util.List;

/**
 * Real HTTP implementation of {@link DataAnalysisClient}, calling Mohammed's Python/FastAPI
 * Data Analyses service via the endpoints agreed in the shared contract (see this class's
 * per-method Javadoc for the exact path each one hits).
 *
 * Active only when `careercompass.ai-service.use-mock=false`. Until Mohammed's service is
 * actually reachable at the configured `careercompass.ai-service.base-url`, flipping this on
 * will simply produce connection/timeout errors from the `.block()` calls below — which is
 * expected and fine; it means the contract is wired correctly and just needs the other side
 * running.
 *
 * Uses WebClient (reactive HTTP client, from spring-boot-starter-webflux — added in
 * Increment 1 specifically for this) but blocks synchronously (`.block()`), since the rest of
 * this Spring MVC application is not reactive — see Increment 1's doc for that reasoning.
 */
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "careercompass.ai-service",
        name = "use-mock",
        havingValue = "false")
public class HttpDataAnalysisClient implements DataAnalysisClient {

    private final WebClient aiServiceWebClient;
    private final AiServiceProperties aiServiceProperties;

    /** POST /transcript-extract */
    @Override
    public TranscriptExtractionResponse extractTranscript(TranscriptExtractionRequest request) {
        return post("/transcript-extract", request, TranscriptExtractionResponse.class);
    }

    /** POST /skill-vector */
    @Override
    public SkillVectorResponse buildSkillVector(BuildSkillVectorRequest request) {
        return post("/skill-vector", request, SkillVectorResponse.class);
    }

    /** POST /skill-gap */
    @Override
    public SkillGapAnalysisResponse analyzeSkillGap(SkillGapAnalysisRequest request) {
        return post("/skill-gap", request, SkillGapAnalysisResponse.class);
    }

    /** POST /course-recommendations */
    @Override
    @SuppressWarnings("unchecked")
    public List<RecommendedCourseDto> recommendCourses(CourseRecommendationRequest request) {
        RecommendedCourseDto[] result = post("/course-recommendations", request, RecommendedCourseDto[].class);
        return result == null ? List.of() : List.of(result);
    }

    /** POST /quiz-generate */
    @Override
    public QuizGenerationResponse generateQuiz(QuizGenerationRequest request) {
        return post("/quiz-generate", request, QuizGenerationResponse.class);
    }

    /** POST /job-match */
    @Override
    public JobMatchResponse scoreJobMatch(JobMatchRequest request) {
        return post("/job-match", request, JobMatchResponse.class);
    }

    private <TReq, TRes> TRes post(String path, TReq requestBody, Class<TRes> responseType) {
        return aiServiceWebClient.post()
                .uri(path)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(responseType)
                .timeout(Duration.ofSeconds(aiServiceProperties.getTimeoutSeconds()))
                .block();
    }
}
