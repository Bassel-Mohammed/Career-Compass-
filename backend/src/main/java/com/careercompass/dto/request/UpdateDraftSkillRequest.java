package com.careercompass.dto.request;

import com.careercompass.entity.SkillDraftDecision;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

/** Partial edit of review metadata and decision for one proposed skill. */
@Getter
@Setter
public class UpdateDraftSkillRequest {

    @Pattern(regexp = "beginner|intermediate|advanced",
            message = "level must be beginner, intermediate, or advanced")
    private String level;

    @DecimalMin(value = "0.0")
    @DecimalMax(value = "1.0")
    @Digits(integer = 1, fraction = 4)
    private BigDecimal weight;

    @Size(max = 500)
    private String note;

    private SkillDraftDecision decision;

    @NotNull(message = "Expected row version is required")
    @PositiveOrZero
    private Long expectedRowVersion;

    @NotNull(message = "Expected draft revision is required")
    @PositiveOrZero
    private Long expectedDraftRevision;
}
