package com.careercompass.dto.response;

import com.fasterxml.jackson.annotation.JsonAlias;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/** One ranked taxonomy alternative returned by the AI matcher. */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DraftSkillCandidateResponse {

    @JsonAlias("id")
    private String skillId;
    private String label;
    private BigDecimal score;
}
