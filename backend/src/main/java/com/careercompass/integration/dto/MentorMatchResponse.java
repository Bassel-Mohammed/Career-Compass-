package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.util.List;

@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MentorMatchResponse {
    private String careerPath;
    private String taxonomyVersion;
    private int total;
    private int gapsConsidered;
    private List<MentorMatchItem> items;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class MentorMatchItem {
        private String mentorId;
        private double score;
        private String signal;
        private List<AlignedSkill> alignedSkills;
        private int gapsAddressed;
        private int yearsExperience;
        private String explanation;
    }

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class AlignedSkill {
        private String skillId;
        private String skillLabel;
    }
}
