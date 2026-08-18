package com.careercompass.util;

import org.springframework.web.multipart.MultipartFile;

/**
 * Shared PDF upload validation, extracted from TranscriptService (Increment 10) so
 * LearningOutcomeService (Increment 15) doesn't duplicate the same three checks. Both FR-JS-10
 * (transcript PDF) and FR-CM-04 (learning outcome PDF) describe the same constraint:
 * text-based PDF only, capped in size.
 */
public final class FileValidationUtils {

    private FileValidationUtils() {
    }

    public static void validatePdf(MultipartFile file, long maxSizeBytes) {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("A file is required.");
        }
        if (file.getSize() > maxSizeBytes) {
            throw new IllegalArgumentException(
                    "File exceeds the " + (maxSizeBytes / (1024 * 1024)) + " MB size limit.");
        }
        String contentType = file.getContentType();
        String filename = file.getOriginalFilename();
        boolean looksLikePdf = "application/pdf".equals(contentType)
                || (filename != null && filename.toLowerCase().endsWith(".pdf"));
        if (!looksLikePdf) {
            throw new IllegalArgumentException("Only PDF files are accepted.");
        }
    }
}
