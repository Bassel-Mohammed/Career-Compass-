package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A proposal-only syllabus extraction submitted to the Python service.
 *
 * <p>{@code storeResults} is deliberately explicit. Content-manager uploads must send
 * {@code false}: the AI output is only a proposal until Java has persisted the review and the
 * content manager publishes an approved map.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SyllabusExtractionRequest {
    private byte[] fileContent;
    private String originalFilename;
    private String contentType;
    private boolean useLlm;
    private boolean force;
    private boolean storeResults;
}
