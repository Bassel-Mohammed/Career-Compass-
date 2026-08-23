package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response for FR-JS-10 (upload transcript) — the "Review what we found" step (Figure 5.4.5)
 * shown to the student BEFORE anything is saved, per NFR-REL-03. Nothing is persisted at this
 * point; the student reviews/edits and then calls the confirm endpoint (see
 * ConfirmTranscriptRequest) to actually trigger FR-JS-11 (persistence).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TranscriptReviewResponse {
    private List<ExtractedCourseItem> courses;
    private int lowConfidenceCount;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ExtractedCourseItem {
        private String courseCode;
        private String courseName;
        private String grade;
        private boolean lowConfidence;
    }
}
