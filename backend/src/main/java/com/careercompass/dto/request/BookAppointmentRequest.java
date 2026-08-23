package com.careercompass.dto.request;

import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * Request body for FR-JS-25 (book a consultation session with a mentor).
 */
@Getter
@Setter
public class BookAppointmentRequest {

    @NotNull(message = "Expert id is required")
    private Integer expertId;

    @NotNull(message = "Appointment date/time is required")
    @Future(message = "Appointment must be scheduled in the future")
    private LocalDateTime appointmentDate;
}
