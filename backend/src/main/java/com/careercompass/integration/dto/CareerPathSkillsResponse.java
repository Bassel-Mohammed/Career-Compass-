package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * What one career path demands, with no student in it.
 *
 * <p>Every other skill response in this package needs a confirmed transcript first, which left
 * the dashboard with nothing to show somebody who has not uploaded one. What a career actually
 * asks for is answerable without knowing anything about them, and it is derived from the same
 * scraped job postings the gap analysis subtracts against — so the two can be read side by side.
 */
@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CareerPathSkillsResponse {

    private String careerPath;

    /** Postings behind this path — the denominator under every {@code coveragePercent}. */
    private Integer sampleSize;

    /** What the requirements were derived from; "job_postings" for the current ontology. */
    private String derivedFrom;

    /**
     * When those postings were collected, ISO-8601. Reported rather than hard-coded so a
     * re-scrape moves the date a UI shows without anybody remembering to edit it.
     */
    private String capturedAt;

    private String taxonomyVersion;

    /** Rows returned, after any band filter. */
    private Integer total;

    /**
     * Rows per band across the whole path, counted before the band filter — so a caller showing
     * one band can still say how big the others are.
     */
    private Map<String, Integer> bandTotals;

    private List<CareerPathSkillDto> skills;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class CareerPathSkillDto {
        private String skillId;
        private String label;
        private String skillType;

        /** Postings that asked for this skill. */
        private Integer postingCount;

        /** Share of the path's postings asking for it, as 0-100 per ADR-003. */
        private BigDecimal coveragePercent;

        /** "critical" / "important" / "useful", banded by the AI service. */
        private String demandBand;

        private String requiredLevel;

        /**
         * A few of the phrases employers actually wrote that resolved to this skill. The reason
         * a student has to believe the number next to it.
         */
        private List<String> sampleTerms;
    }
}
