package com.careercompass.dto.request;

import lombok.Getter;
import lombok.Setter;

/**
 * Request body for FR-EX-09/10/11 (feedback, readiness evaluation, session notes),
 * submitted together after a consultation session. `feedback` doubles as the vehicle for the
 * FR-EX-10 readiness evaluation — see AppointmentService's Javadoc for why (the `appointments`
 * table has no dedicated readiness column).
 */
@Getter
@Setter
public class ConsultationOutcomeRequest {
    private String sessionNotes;
    private String feedback;
}
