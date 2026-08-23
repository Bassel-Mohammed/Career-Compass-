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
 * This is the transport-neutral request used by the Java business layer. The HTTP adapter
 * turns these bytes into the multipart {@code file} part expected by FastAPI. A Java database
 * job-seeker id is intentionally not part of this request: database-local numeric identifiers
 * must never become cross-service identities.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TranscriptExtractionRequest {
    private byte[] fileContent;
    private String originalFilename;
    private String contentType;
}
