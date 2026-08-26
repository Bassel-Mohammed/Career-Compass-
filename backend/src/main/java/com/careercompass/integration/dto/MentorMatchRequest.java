package com.careercompass.integration.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Getter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MentorMatchRequest {
    private String careerPathName;
    private List<CourseGradeDto> courses;
    private Map<String, BigDecimal> quizScores;

    @Builder.Default
    private boolean includeSoft = true;

    @Builder.Default
    private boolean narrative = false;

    private List<MentorDto> mentors;
    
    @Builder.Default
    private int limit = 10;

    @Getter
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class MentorDto {
        private String mentorId;
        private String studyField;
        private Integer fieldStartingYear;
        private List<String> expertiseTerms;
    }
}
