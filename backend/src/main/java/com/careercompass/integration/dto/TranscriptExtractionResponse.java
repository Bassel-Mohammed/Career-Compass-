package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response from Module 1. `lowConfidence` on each row drives the "2 rows were read with low
 * confidence and are flagged for your review" banner in the report's UI mockup (Figure 5.4.5)
 * — the extraction is shown to the student for review/correction BEFORE anything is persisted
 * (Section 5.3.3: "confirmed by the student before persistence; malformed or low-confidence
 * extractions are rejected or flagged rather than silently stored" — NFR-REL-03).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TranscriptExtractionResponse {
    private List<ExtractedCourseDto> courses;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ExtractedCourseDto {
        private String courseCode;
        private String courseName;
        private String grade;
        private boolean lowConfidence;
    }
}
