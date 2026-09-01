package com.careercompass.integration.ai;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Binds the {@code careercompass.ai-service.*} block from application.yml.
 *
 * <p>{@code useMock} is what {@link MockDataAnalysisClient} and {@link HttpDataAnalysisClient}
 * switch on. It defaults to {@code true} so a developer with no Python service running still
 * gets a working backend — but the {@code prod} and {@code integration} profiles set it to
 * {@code false} explicitly, because a production deployment quietly serving mock skill scores is
 * far worse than one that fails to start.
 */
@Component
@ConfigurationProperties(prefix = "careercompass.ai-service")
@Getter
@Setter
public class AiServiceProperties {

    private String baseUrl;
    private boolean useMock = true;

    /** Fallback deadline for any operation without its own budget. */
    private long timeoutSeconds = 30;

    /**
     * Bearer token authenticating this backend to the AI service (ADR-008). Blank is tolerated
     * on loopback for local development; the production profile requires it.
     */
    private String token;

    private Timeouts timeouts = new Timeouts();

    /**
     * Per-operation deadlines in seconds, from the NFR budgets. One shared 30-second timeout let
     * a five-second operation hang a request thread for thirty, so the dashboard and the
     * transcript upload failed on the same schedule despite having very different budgets.
     */
    @Getter
    @Setter
    public static class Timeouts {
        /** NFR-PERF-02: transcript processing. */
        private long transcriptSeconds = 30;
        /** Dashboard/vector budget. */
        private long skillVectorSeconds = 10;
        /** Dashboard/gap budget. */
        private long skillGapSeconds = 10;
        /** Recommendation retrieval target. */
        private long recommendationsSeconds = 5;
        /** Quiz generation budget — an LLM call, so the longest of the JSON operations. */
        private long quizSeconds = 15;
        /** Syllabus submit performs parsing before returning the asynchronous operation id. */
        private long syllabusSeconds = 30;
        /** Taxonomy search and approved map publication are deterministic storage operations. */
        private long taxonomySeconds = 10;
        private long publicationSeconds = 30;
    }
}
