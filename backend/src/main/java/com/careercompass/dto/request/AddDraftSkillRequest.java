package com.careercompass.dto.request;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

import java.math.BigDecimal;

/** Adds a human-selected canonical skill to the current review draft. */
@Getter
@Setter
public class AddDraftSkillRequest {

    @NotBlank(message = "Canonical skill id is required")
    @Size(max = 120)
    private String skillId;

    /** Display label from the taxonomy picker; the backend re-resolves it against the taxonomy. */
    @Size(max = 200)
    private String skillLabel;

    @Size(max = 200)
    private String term;

    @NotBlank(message = "Skill level is required")
    @Pattern(regexp = "beginner|intermediate|advanced",
            message = "level must be beginner, intermediate, or advanced")
    private String level;

    @NotNull(message = "Skill weight is required")
    @DecimalMin(value = "0.0")
    @DecimalMax(value = "1.0")
    @Digits(integer = 1, fraction = 4)
    private BigDecimal weight;

    @Size(max = 500)
    private String note;

    @NotNull(message = "Expected draft revision is required")
    @PositiveOrZero
    private Long expectedDraftRevision;
}
