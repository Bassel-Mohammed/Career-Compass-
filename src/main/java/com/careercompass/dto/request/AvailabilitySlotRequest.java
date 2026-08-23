package com.careercompass.dto.request;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalTime;

/**
 * A single weekly availability slot (FR-EX-06). `dayOfWeek` is 1-7, matching the DB CHECK
 * constraint `chk_day_of_week` on `expert_availability`.
 */
@Getter
@Setter
public class AvailabilitySlotRequest {

    @NotNull
    @Min(1) @Max(7)
    private Integer dayOfWeek;

    @NotNull
    private LocalTime startTime;

    @NotNull
    private LocalTime endTime;
}
