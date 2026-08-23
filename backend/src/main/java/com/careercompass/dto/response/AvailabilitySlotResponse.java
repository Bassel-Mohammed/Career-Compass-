package com.careercompass.dto.response;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalTime;

@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AvailabilitySlotResponse {
    private Integer availabilityId;
    private Integer dayOfWeek;
    private LocalTime startTime;
    private LocalTime endTime;
}
