package com.careercompass.config;

import com.careercompass.integration.ai.AiServiceProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * Builds the {@link WebClient} used by {@link com.careercompass.integration.ai.HttpDataAnalysisClient}
 * to call Mohammed's Python/FastAPI Data Analyses service. Only ever instantiated/used when
 * `careercompass.ai-service.use-mock=false` (see AiServiceProperties) — while the mock client
 * is active, this bean still exists but nothing calls it.
 */
@Configuration
@RequiredArgsConstructor
public class WebClientConfig {

    private final AiServiceProperties aiServiceProperties;

    @Bean
    public WebClient aiServiceWebClient() {
        return WebClient.builder()
                .baseUrl(aiServiceProperties.getBaseUrl())
                .build();
    }
}
