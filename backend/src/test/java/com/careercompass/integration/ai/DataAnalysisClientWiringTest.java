package com.careercompass.integration.ai;

import com.careercompass.config.WebClientConfig;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Confirms the `careercompass.ai-service.use-mock` property correctly switches which
 * DataAnalysisClient implementation is active (NFR-MNT-01/02: swappable by configuration,
 * not code change) — this is the actual mechanism the whole mock-first development strategy
 * depends on, so it's worth a dedicated test rather than just trusting the annotations.
 *
 * Registers the real {@code @Component}-annotated classes (not hand-built substitutes) so
 * Spring's condition evaluation actually runs against the same {@code @ConditionalOnProperty}
 * annotations used in production — a hand-instantiated `@Bean` method would silently bypass
 * those conditions entirely.
 */
class DataAnalysisClientWiringTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(
                    PropertiesConfig.class,
                    WebClientConfig.class,
                    MockDataAnalysisClient.class,
                    HttpDataAnalysisClient.class)
            .withPropertyValues("careercompass.ai-service.base-url=http://localhost:9999");

    // Purpose: Mock Client Is Active When Use Mock Is True.
    @Test
    void mockClientIsActiveWhenUseMockIsTrue() {
        contextRunner
                .withPropertyValues("careercompass.ai-service.use-mock=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(DataAnalysisClient.class);
                    assertThat(context.getBean(DataAnalysisClient.class))
                            .isInstanceOf(MockDataAnalysisClient.class);
                });
    }

    // Purpose: Mock Client Is Active By Default When Property Is Absent.
    @Test
    void mockClientIsActiveByDefaultWhenPropertyIsAbsent() {
        // matchIfMissing = true on MockDataAnalysisClient — confirms the safe default.
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(DataAnalysisClient.class);
            assertThat(context.getBean(DataAnalysisClient.class)).isInstanceOf(MockDataAnalysisClient.class);
        });
    }

    // Purpose: Http Client Is Active When Use Mock Is False.
    @Test
    void httpClientIsActiveWhenUseMockIsFalse() {
        contextRunner
                .withPropertyValues("careercompass.ai-service.use-mock=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(DataAnalysisClient.class);
                    assertThat(context.getBean(DataAnalysisClient.class))
                            .isInstanceOf(HttpDataAnalysisClient.class);
                });
    }

    /**
     * Enables real Spring Boot @ConfigurationProperties binding (careercompass.ai-service.*
     * -> AiServiceProperties) within the lightweight ApplicationContextRunner, so
     * WebClientConfig's `aiServiceProperties.getBaseUrl()` is actually populated instead of
     * null (which would otherwise fail WebClient.builder().baseUrl(...) at context startup,
     * unrelated to what this test is trying to verify).
     */
    @Configuration
    @EnableConfigurationProperties(AiServiceProperties.class)
    static class PropertiesConfig {
    }
}
