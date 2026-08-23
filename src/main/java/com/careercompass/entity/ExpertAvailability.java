package com.careercompass.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalTime;

/**
 * Maps to the `expert_availability` table.
 * A recurring weekly availability slot for an Expert (FR-EX-06).
 * `dayOfWeek` is 1-7 (DB CHECK `chk_day_of_week`); `startTime` &lt; `endTime`
 * (DB CHECK `chk_time_range`) — both also validated in the service layer.
 */
@Entity
@Table(name = "expert_availability")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ExpertAvailability {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "availability_id")
    private Integer availabilityId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "expert_id", nullable = false)
    private Expert expert;

    /** 1 = Monday ... 7 = Sunday (convention to be confirmed with the team). */
    @Column(name = "day_of_week", nullable = false)
    private Byte dayOfWeek;

    @Column(name = "start_time", nullable = false)
    private LocalTime startTime;

    @Column(name = "end_time", nullable = false)
    private LocalTime endTime;
}
