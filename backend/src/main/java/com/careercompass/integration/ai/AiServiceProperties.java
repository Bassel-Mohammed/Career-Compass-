package com.careercompass.integration.ai;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Binds the `careercompass.ai-service.*` block from application.yml (scaffolded in
 * Increment 1). `useMock` is what {@link MockDataAnalysisClient} and
 * {@link HttpDataAnalysisClient}'s {@code @ConditionalOnProperty} switch on.
 */
@Component
@ConfigurationProperties(prefix = "careercompass.ai-service")
@Getter
@Setter
public class AiServiceProperties {

    private String baseUrl;
    private boolean useMock = true;
    private long timeoutSeconds = 30;
}
