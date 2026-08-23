package com.careercompass.integration.ai;

import com.careercompass.integration.dto.*;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit tests for MockDataAnalysisClient's fake-but-realistic logic — not testing "AI
 * correctness" (there is none, it's a mock), but confirming the mock produces well-formed,
 * usable responses that downstream services (built in later increments) can develop against.
 */
class MockDataAnalysisClientTest {

    private final MockDataAnalysisClient client = new MockDataAnalysisClient();

    // Purpose: Build Skill Vector - returns One Score Per Course.
    @Test
    void buildSkillVector_returnsOneScorePerCourse() {
        BuildSkillVectorRequest request = BuildSkillVectorRequest.builder()
                .jobseekerId(1)
                .careerPathId(1)
                .courses(List.of(
                        CourseGradeDto.builder().courseName("Data Structures").grade("A").build(),
                        CourseGradeDto.builder().courseName("Operating Systems").grade("C").build()
                ))
                .build();

        SkillVectorResponse response = client.buildSkillVector(request);

        assertThat(response.getSkills()).hasSize(2);
        // Higher grade should map to a higher score.
        BigDecimal dataStructuresScore = response.getSkills().get(0).getScore();
        BigDecimal osScore = response.getSkills().get(1).getScore();
        assertThat(dataStructuresScore).isGreaterThan(osScore);
    }

    // Purpose: Analyze Skill Gap - classifies High Score As Strong.
    @Test
    void analyzeSkillGap_classifiesHighScoreAsStrong() {
        // An A grade drives the mock's grade-based score high enough to classify as Strong.
        SkillGapAnalysisRequest request = SkillGapAnalysisRequest.builder()
                .careerPathName("Backend Development")
                .courses(List.of(
                        CourseGradeDto.builder().courseCode("CS201").courseName("Algorithms").grade("A").build()
                ))
                .build();

        SkillGapAnalysisResponse response = client.analyzeSkillGap(request);

        assertThat(response.getSkillGaps()).hasSize(1);
        assertThat(response.getSkillGaps().get(0).getClassification()).isEqualTo("Strong");
        // The canonical id must travel with the gap: it is what a quiz request and the
        // FR-JS-20/21 write-back key on.
        assertThat(response.getSkillGaps().get(0).getSkillId()).isNotBlank();
        assertThat(response.getSkillGaps().get(0).getExplanation()).isNotBlank();
    }

    // Purpose: Analyze Skill Gap - classifies Low Score As Weak.
    @Test
    void analyzeSkillGap_classifiesLowScoreAsWeak() {
        // A failing grade drives the mock's score low enough to classify as Weak.
        SkillGapAnalysisRequest request = SkillGapAnalysisRequest.builder()
                .careerPathName("DevOps & Cloud")
                .courses(List.of(
                        CourseGradeDto.builder().courseCode("OPS101").courseName("DevOps").grade("F").build()
                ))
                .build();

        SkillGapAnalysisResponse response = client.analyzeSkillGap(request);

        assertThat(response.getSkillGaps().get(0).getClassification()).isEqualTo("Weak");
    }

    // Purpose: Recommend Courses - returns One Course Per Weak Skill.
    @Test
    void recommendCourses_returnsOneCoursePerWeakSkill() {
        // Both courses are failed, so both become weak gaps the mock recommends against.
        CourseRecommendationRequest request = CourseRecommendationRequest.builder()
                .careerPathName("DevOps & Cloud")
                .courses(List.of(
                        CourseGradeDto.builder().courseCode("OPS101").courseName("DevOps").grade("F").build(),
                        CourseGradeDto.builder().courseCode("OPS102").courseName("Cloud Computing").grade("F").build()
                ))
                .build();

        List<RecommendedCourseDto> recommendations = client.recommendCourses(request);

        assertThat(recommendations).hasSize(2);
        assertThat(recommendations).allSatisfy(r -> {
            assertThat(r.getCourseName()).isNotBlank();
            // NFR-AI-05: every recommendation must point at something the student can open.
            assertThat(r.getSourceLink()).startsWith("https://");
            assertThat(r.getTargetedSkillId()).isNotBlank();
        });
    }

    // Purpose: Generate Quiz - returns Requested Question Count With Exactly One Correct Option Each.
    @Test
    void generateQuiz_returnsRequestedQuestionCountWithExactlyOneCorrectOptionEach() {
        QuizGenerationRequest request = QuizGenerationRequest.builder()
                .skillId("custom:databases")
                .questionCount(5)
                .build();

        QuizGenerationResponse response = client.generateQuiz(request);

        assertThat(response.getQuestions()).hasSize(5);
        // NFR-AI-07: exactly one correct option per question — confirm the mock at least
        // always sets a valid single-letter option, matching the shape real responses must have.
        assertThat(response.getQuestions()).allSatisfy(q ->
                assertThat(q.getCorrectOption()).isIn("A", "B", "C", "D"));
    }

    // Purpose: Score Job Match - returns Score Within Valid Range.
    @Test
    void scoreJobMatch_returnsScoreWithinValidRange() {
        JobMatchRequest request = JobMatchRequest.builder()
                .skillVector(List.of(
                        SkillScoreDto.builder().skillName("Java").score(BigDecimal.valueOf(80)).build(),
                        SkillScoreDto.builder().skillName("SQL").score(BigDecimal.valueOf(70)).build()
                ))
                .jobTitle("Backend Engineer")
                .jobDescription("Build APIs")
                .jobRequiredSkills("Java, SQL")
                .build();

        JobMatchResponse response = client.scoreJobMatch(request);

        assertThat(response.getMatchScore()).isGreaterThanOrEqualTo(BigDecimal.ZERO);
        assertThat(response.getMatchScore()).isLessThanOrEqualTo(BigDecimal.valueOf(100));
        assertThat(response.getExplanation()).isNotBlank();
    }
}
