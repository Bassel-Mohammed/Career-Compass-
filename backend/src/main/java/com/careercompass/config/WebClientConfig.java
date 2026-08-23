package com.careercompass.config;

import com.careercompass.integration.ai.AiServiceProperties;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.UUID;

/**
 * Builds the {@link WebClient} used by {@link com.careercompass.integration.ai.HttpDataAnalysisClient}
 * to call the Python/FastAPI Data Analyses service.
 *
 * <p>Two filters are attached rather than being repeated at each call site:
 *
 * <ul>
 *   <li><b>Service authentication.</b> A bearer token identifying this backend, not a student —
 *       no end-user identity crosses this boundary.</li>
 *   <li><b>Correlation.</b> One id per outbound call, reused from the MDC when the incoming
 *       request already established one. Without it, a student-visible failure has to be traced
 *       by matching timestamps across two runtimes' logs.</li>
 * </ul>
 *
 * <p>The bean exists even while the mock client is active; nothing calls it then.
 */
@Configuration
@RequiredArgsConstructor
public class WebClientConfig {

    /** Header name shared with the AI service; it echoes this back on problem responses. */
    public static final String CORRELATION_ID_HEADER = "X-Correlation-ID";

    /** MDC key an inbound request filter can populate so both hops share one id. */
    public static final String CORRELATION_ID_MDC_KEY = "correlationId";

    private final AiServiceProperties aiServiceProperties;

    @Bean
    public WebClient aiServiceWebClient() {
        WebClient.Builder builder = WebClient.builder()
                .baseUrl(aiServiceProperties.getBaseUrl())
                .filter(correlationIdFilter());

        if (StringUtils.hasText(aiServiceProperties.getToken())) {
            builder.filter(serviceTokenFilter(aiServiceProperties.getToken()));
        }

        return builder.build();
    }

    private ExchangeFilterFunction correlationIdFilter() {
        return (request, next) -> {
            String correlationId = MDC.get(CORRELATION_ID_MDC_KEY);
            if (!StringUtils.hasText(correlationId)) {
                correlationId = UUID.randomUUID().toString();
            }
            return next.exchange(ClientRequest.from(request)
                    .header(CORRELATION_ID_HEADER, correlationId)
                    .build());
        };
    }

    private ExchangeFilterFunction serviceTokenFilter(String token) {
        return (request, next) -> next.exchange(ClientRequest.from(request)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .build());
    }
}
