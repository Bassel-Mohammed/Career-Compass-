package com.careercompass.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

/**
 * Request body for confirming/persisting a reviewed transcript (FR-JS-11), sent after the
 * student has reviewed and possibly corrected the rows from TranscriptReviewResponse
 * (Figure 5.4.5's "Confirm & build my profile" action). This is a deliberately separate step
 * from upload — see TranscriptReviewResponse's Javadoc.
 */
@Getter
@Setter
public class ConfirmTranscriptRequest {

    @NotEmpty(message = "At least one course is required")
    @Valid
    private List<CourseGradeItem> courses;

    @Getter
    @Setter
    public static class CourseGradeItem {

        /**
         * Stable course identity used by the AI service. Nullable only so existing clients and
         * pre-migration records can still be reviewed; transcript extraction always supplies it.
         */
        private String courseCode;

        @NotBlank(message = "Course name is required")
        private String courseName;

        @NotBlank(message = "Grade is required")
        private String grade;
    }
}
