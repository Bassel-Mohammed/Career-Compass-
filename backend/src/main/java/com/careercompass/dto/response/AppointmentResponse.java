package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * An appointment, shown to either party (Expert or Job Seeker). Includes both names so
 * either side's UI can render it without a second lookup.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AppointmentResponse {
    private Integer appointmentId;
    private Integer expertId;
    private String expertName;
    private Integer jobseekerId;
    private String jobseekerName;
    private LocalDateTime appointmentDate;
    private String statusName;
    private String sessionNotes;
    private String feedback;
    private LocalDateTime createdAt;
}
