package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Request to Module 1 (Transcript Analysis, Section 5.3.3): "the uploaded transcript PDF is
 * parsed with pdfplumber, and an LLM converts the raw text into structured JSON." Both steps
 * happen inside the Python service, not in Java — Java's only job is to receive the upload
 * from the job seeker (FR-JS-10) and forward the raw bytes here.
 *
 * The PDF is sent base64-encoded in the JSON body rather than as multipart, since this is a
 * service-to-service call over the same WebClient/DataAnalysisClient contract as every other
 * module — simpler than mixing multipart and JSON call styles for one endpoint.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TranscriptExtractionRequest {
    private Integer jobseekerId;
    private String fileBase64;
    private String originalFilename;
}
