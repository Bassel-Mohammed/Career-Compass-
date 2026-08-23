package com.careercompass.service;

import com.careercompass.dto.request.GenerateQuizRequest;
import com.careercompass.dto.request.SubmitQuizRequest;
import com.careercompass.dto.response.QuizResultResponse;
import com.careercompass.dto.response.QuizView;
import com.careercompass.dto.response.SkillDashboardResponse;
import com.careercompass.entity.JobSeeker;
import com.careercompass.entity.Quiz;
import com.careercompass.entity.QuizQuestion;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.QuizGenerationRequest;
import com.careercompass.integration.dto.QuizGenerationResponse;
import com.careercompass.repository.JobSeekerRepository;
import com.careercompass.repository.QuizRepository;
import com.careercompass.repository.QuizResponseRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for QuizService. Verifies: NFR-AI-07 filtering of malformed AI-generated
 * questions, the ownership check (same pattern as JobService's, Increment 8), no-retake
 * enforcement, correct scoring, and — importantly — that submitting a quiz triggers
 * TranscriptService's dashboard recompute rather than writing to jobseeker_skills directly
 * (see QuizService's class Javadoc on why there is exactly one writer of that table).
 */
@ExtendWith(MockitoExtension.class)
class QuizServiceTest {

    @Mock private JobSeekerRepository jobSeekerRepository;
    @Mock private QuizRepository quizRepository;
    @Mock private QuizResponseRepository quizResponseRepository;
    @Mock private DataAnalysisClient dataAnalysisClient;
    @Mock private TranscriptService transcriptService;

    @InjectMocks
    private QuizService quizService;

    // Purpose: Generate Quiz - filters Out Questions With Invalid Correct Option.
    @Test
    void generateQuiz_filtersOutQuestionsWithInvalidCorrectOption() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));

        when(dataAnalysisClient.generateQuiz(any(QuizGenerationRequest.class)))
                .thenReturn(QuizGenerationResponse.builder()
                        .questions(List.of(
                                validQuestion("A"),
                                // Malformed: correctOption "E" is not A/B/C/D — must be dropped (NFR-AI-07).
                                QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                                        .questionText("Bad question")
                                        .optionA("a").optionB("b").optionC("c").optionD("d")
                                        .correctOption("E")
                                        .build()
                        ))
                        .build());

        when(quizRepository.save(any(Quiz.class))).thenAnswer(inv -> {
            Quiz q = inv.getArgument(0);
            if (q.getQuizId() == null) {
                q.setQuizId(10);
            }
            return q;
        });

        GenerateQuizRequest request = new GenerateQuizRequest();
        request.setSkillId("custom:databases");
        request.setQuestionCount(2);

        QuizView view = quizService.generateQuiz(1, request);

        assertThat(view.getQuestions()).hasSize(1); // only the valid one survives
    }

    // Purpose: Generate Quiz - throws When No Valid Questions Survive.
    @Test
    void generateQuiz_throwsWhenNoValidQuestionsSurvive() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();
        when(jobSeekerRepository.findById(1)).thenReturn(Optional.of(jobSeeker));

        when(dataAnalysisClient.generateQuiz(any(QuizGenerationRequest.class)))
                .thenReturn(QuizGenerationResponse.builder()
                        .questions(List.of(QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                                .questionText("Bad question")
                                .optionA("a").optionB("b").optionC("c").optionD("d")
                                .correctOption("Z")
                                .build()))
                        .build());

        GenerateQuizRequest request = new GenerateQuizRequest();
        request.setSkillId("custom:databases");
        request.setQuestionCount(1);

        assertThatThrownBy(() -> quizService.generateQuiz(1, request))
                .isInstanceOf(IllegalStateException.class);

        verify(quizRepository, never()).save(any());
    }

    // Purpose: Get Quiz - throws Unauthorized When Caller Does Not Own The Quiz.
    @Test
    void getQuiz_throwsUnauthorizedWhenCallerDoesNotOwnTheQuiz() {
        JobSeeker owner = JobSeeker.builder().jobseekerId(1).build();
        Quiz quiz = Quiz.builder().quizId(5).jobSeeker(owner).build();

        when(quizRepository.findById(5)).thenReturn(Optional.of(quiz));

        assertThatThrownBy(() -> quizService.getQuiz(2, 5))
                .isInstanceOf(UnauthorizedActionException.class);
    }

    // Purpose: Submit Quiz - throws When Already Taken.
    @Test
    void submitQuiz_throwsWhenAlreadyTaken() {
        JobSeeker owner = JobSeeker.builder().jobseekerId(1).build();
        Quiz quiz = Quiz.builder().quizId(5).jobSeeker(owner)
                .takenAt(java.time.LocalDateTime.now()).build();

        when(quizRepository.findById(5)).thenReturn(Optional.of(quiz));

        SubmitQuizRequest request = new SubmitQuizRequest();
        assertThatThrownBy(() -> quizService.submitQuiz(1, 5, request))
                .isInstanceOf(PrerequisiteNotMetException.class);
    }

    // Purpose: Submit Quiz - scores Correctly And Triggers Dashboard Recompute.
    @Test
    void submitQuiz_scoresCorrectlyAndTriggersDashboardRecompute() {
        JobSeeker jobSeeker = JobSeeker.builder().jobseekerId(1).build();

        QuizQuestion q1 = QuizQuestion.builder().questionId(101).correctOption("A").build();
        QuizQuestion q2 = QuizQuestion.builder().questionId(102).correctOption("B").build();

        Quiz quiz = Quiz.builder().quizId(5).jobSeeker(jobSeeker).courseName("Databases").build();
        quiz.getQuestions().add(q1);
        quiz.getQuestions().add(q2);

        when(quizRepository.findById(5)).thenReturn(Optional.of(quiz));
        when(quizRepository.save(any(Quiz.class))).thenAnswer(inv -> inv.getArgument(0));

        SubmitQuizRequest request = new SubmitQuizRequest();
        var a1 = new SubmitQuizRequest.QuizAnswerItem();
        a1.setQuestionId(101);
        a1.setSelectedOption("A"); // correct
        var a2 = new SubmitQuizRequest.QuizAnswerItem();
        a2.setQuestionId(102);
        a2.setSelectedOption("C"); // incorrect (correct is B)
        request.setAnswers(List.of(a1, a2));

        SkillDashboardResponse fakeDashboard = SkillDashboardResponse.builder().basedOnQuizResults(true).build();
        when(transcriptService.getSkillDashboard(1)).thenReturn(fakeDashboard);

        QuizResultResponse result = quizService.submitQuiz(1, 5, request);

        assertThat(result.getCorrectCount()).isEqualTo(1);
        assertThat(result.getTotalQuestions()).isEqualTo(2);
        assertThat(result.getScore()).isEqualByComparingTo(BigDecimal.valueOf(50.00));
        assertThat(result.getUpdatedDashboard()).isSameAs(fakeDashboard);

        verify(quizResponseRepository, times(2)).save(any());
        verify(transcriptService).getSkillDashboard(1); // confirms the single-writer handoff
    }

    private QuizGenerationResponse.GeneratedQuizQuestionDto validQuestion(String correctOption) {
        return QuizGenerationResponse.GeneratedQuizQuestionDto.builder()
                .questionText("Valid question")
                .optionA("a").optionB("b").optionC("c").optionD("d")
                .correctOption(correctOption)
                .build();
    }
}
