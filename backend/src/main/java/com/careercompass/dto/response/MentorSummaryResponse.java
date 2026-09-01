package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import java.math.BigDecimal;
import java.util.List;

/**
 * A mentor/expert as browsable by a job seeker (FR-JS-24).
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MentorSummaryResponse {
    private Integer expertId;
    private String firstName;
    private String lastName;
    private String studyFieldName;
    private Short fieldStartingYear;
    private BigDecimal matchScore;
    private Integer gapsAddressed;
    private String matchReason;

    /**
     * The mentor's published weekly schedule, so the booking form can offer real times.
     *
     * <p>Booking rejects anything outside these slots. Without them on this response the
     * student had a free date-time field and no way to know what would be accepted — they
     * could only guess and read the rejection.
     *
     * <p>Empty means the mentor has not published a schedule and cannot be booked yet.
     */
    private List<AvailabilitySlotResponse> availability;
}
