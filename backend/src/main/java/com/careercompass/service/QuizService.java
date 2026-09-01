package com.careercompass.service;

import com.careercompass.dto.request.GenerateQuizRequest;
import com.careercompass.dto.request.SubmitQuizRequest;
import com.careercompass.dto.response.QuizQuestionView;
import com.careercompass.dto.response.QuizResultResponse;
import com.careercompass.dto.response.QuizView;
import com.careercompass.entity.JobSeeker;
import com.careercompass.entity.Quiz;
import com.careercompass.entity.QuizQuestion;
import com.careercompass.entity.QuizResponse;
import com.careercompass.exception.PrerequisiteNotMetException;
import com.careercompass.exception.ResourceNotFoundException;
import com.careercompass.exception.UnauthorizedActionException;
import com.careercompass.integration.ai.DataAnalysisClient;
import com.careercompass.integration.dto.QuizGenerationRequest;
import com.careercompass.integration.dto.QuizGenerationResponse;
import com.careercompass.repository.JobSeekerRepository;
import com.careercompass.repository.QuizRepository;
import com.careercompass.repository.QuizResponseRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.HashSet;
import java.util.Set;

/**
 * Business Layer for FR-JS-17/18/19 (generate, attempt, evaluate quizzes).
 *
 * Deliberately does NOT write to {@code jobseeker_skills} itself — see
 * {@link TranscriptService}'s Javadoc for why skill persistence has a single owner. After a
 * quiz is submitted, this service simply asks {@link TranscriptService} to recompute the
 * dashboard, which is where the FR-JS-20 write-back actually happens (by finding this
 * newly-completed quiz). This keeps exactly one code path that ever writes a
 * {@code jobseeker_skills} row, avoiding the two-writers problem that would otherwise let a
 * later dashboard fetch silently overwrite what this service just set.
 */
@Service
@RequiredArgsConstructor
public class QuizService {

    private static final List<String> VALID_OPTIONS = List.of("A", "B", "C", "D");

    private final JobSeekerRepository jobSeekerRepository;
    private final QuizRepository quizRepository;
    private final QuizResponseRepository quizResponseRepository;
    private final DataAnalysisClient dataAnalysisClient;
    private final TranscriptService transcriptService;

    /** FR-JS-17: generate a quiz for one of the job seeker's skills. */
    @Transactional
    public QuizView generateQuiz(Integer jobseekerId, GenerateQuizRequest request) {
        JobSeeker jobSeeker = jobSeekerRepository.findById(jobseekerId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Job seeker with id " + jobseekerId + " not found."));

        QuizGenerationResponse generated = dataAnalysisClient.generateQuiz(
                QuizGenerationRequest.builder()
                        .skillId(request.getSkillId())
                        .questionCount(request.getQuestionCount())
                        .build());

        // NFR-AI-07: exactly one correct option per question, validated programmatically
        // (not trusted from the AI response) before persistence — malformed questions are
        // dropped rather than silently stored, mirroring NFR-REL-03's transcript-review
        // philosophy applied to quiz generation.
        List<QuizGenerationResponse.GeneratedQuizQuestionDto> validQuestions = generated.getQuestions().stream()
                .filter(this::hasExactlyOneValidCorrectOption)
                .toList();

        if (validQuestions.isEmpty()) {
            throw new IllegalStateException(
                    "The AI service did not return any well-formed quiz questions. Please try again.");
        }

        // The canonical id is stored alongside the label because it, not the label, is what the
        // FR-JS-20/21 write-back joins on when the dashboard is next recomputed.
        String skillLabel = generated.getSkillLabel() != null
                ? generated.getSkillLabel()
                : request.getSkillId();

        Quiz quiz = Quiz.builder()
                .jobSeeker(jobSeeker)
                .skillId(request.getSkillId())
                .courseName(skillLabel)
                .build();
        quiz = quizRepository.save(quiz);

        for (QuizGenerationResponse.GeneratedQuizQuestionDto q : validQuestions) {
            QuizQuestion question = QuizQuestion.builder()
                    .quiz(quiz)
                    .questionText(q.getQuestionText())
                    .optionA(q.getOptionA())
                    .optionB(q.getOptionB())
                    .optionC(q.getOptionC())
                    .optionD(q.getOptionD())
                    .correctOption(q.getCorrectOption().toUpperCase())
                    .build();
            quiz.getQuestions().add(question);
        }
        quiz = quizRepository.save(quiz);

        return toQuizView(quiz);
    }

    /** FR-JS-18: view a quiz to attempt it (no correct answers included). */
    @Transactional(readOnly = true)
    public QuizView getQuiz(Integer jobseekerId, Integer quizId) {
        Quiz quiz = getOwnedQuizOrThrow(jobseekerId, quizId);
        return toQuizView(quiz);
    }

    /** FR-JS-19/20/21: submit answers, evaluate, persist responses, and refresh the dashboard. */
    @Transactional
    public QuizResultResponse submitQuiz(Integer jobseekerId, Integer quizId, SubmitQuizRequest request) {
        Quiz quiz = getOwnedQuizOrThrow(jobseekerId, quizId);

        if (quiz.getTakenAt() != null) {
            throw new PrerequisiteNotMetException("This quiz has already been submitted.");
        }

        Map<Integer, QuizQuestion> questionsById = quiz.getQuestions().stream()
                .collect(java.util.stream.Collectors.toMap(QuizQuestion::getQuestionId, q -> q));

        Set<Integer> submittedQuestionIds = new HashSet<>();
        for (SubmitQuizRequest.QuizAnswerItem answer : request.getAnswers()) {
            if (!submittedQuestionIds.add(answer.getQuestionId())) {
                throw new IllegalArgumentException(
                        "Question " + answer.getQuestionId() + " was answered more than once.");
            }
        }

        int correctCount = 0;
        List<QuizResultResponse.QuestionResult> results = new java.util.ArrayList<>();

        for (SubmitQuizRequest.QuizAnswerItem answer : request.getAnswers()) {
            QuizQuestion question = questionsById.get(answer.getQuestionId());
            if (question == null) {
                throw new IllegalArgumentException(
                        "Question with id " + answer.getQuestionId() + " does not belong to this quiz.");
            }

            String selected = answer.getSelectedOption().toUpperCase();
            boolean isCorrect = question.getCorrectOption().equalsIgnoreCase(selected);
            if (isCorrect) {
                correctCount++;
            }

            quizResponseRepository.save(QuizResponse.builder()
                    .question(question)
                    .selectedOption(selected)
                    .isCorrect(isCorrect)
                    .build());

            results.add(QuizResultResponse.QuestionResult.builder()
                    .questionId(question.getQuestionId())
                    .selectedOption(selected)
                    .correctOption(question.getCorrectOption())
                    .correct(isCorrect)
                    .build());
        }

        int totalQuestions = quiz.getQuestions().size();
        BigDecimal score = totalQuestions == 0
                ? BigDecimal.ZERO
                : BigDecimal.valueOf(correctCount)
                        .divide(BigDecimal.valueOf(totalQuestions), 4, RoundingMode.HALF_UP)
                        .multiply(BigDecimal.valueOf(100))
                        .setScale(2, RoundingMode.HALF_UP);

        quiz.setScore(score);
        quiz.setTakenAt(LocalDateTime.now());
        quizRepository.save(quiz);

        // FR-JS-20/21: recompute the dashboard now that a completed quiz exists for this
        // course — TranscriptService will find it and apply the write-back (see its Javadoc).
        var updatedDashboard = transcriptService.getSkillDashboard(jobseekerId);

        return QuizResultResponse.builder()
                .quizId(quiz.getQuizId())
                .score(score)
                .correctCount(correctCount)
                .totalQuestions(totalQuestions)
                .questionResults(results)
                .updatedDashboard(updatedDashboard)
                .build();
    }

    private boolean hasExactlyOneValidCorrectOption(QuizGenerationResponse.GeneratedQuizQuestionDto q) {
        return q.getCorrectOption() != null
                && VALID_OPTIONS.contains(q.getCorrectOption().toUpperCase());
    }

    private Quiz getOwnedQuizOrThrow(Integer jobseekerId, Integer quizId) {
        Quiz quiz = quizRepository.findById(quizId)
                .orElseThrow(() -> new ResourceNotFoundException("Quiz with id " + quizId + " not found."));

        if (!quiz.getJobSeeker().getJobseekerId().equals(jobseekerId)) {
            throw new UnauthorizedActionException("You do not have permission to access this quiz.");
        }

        return quiz;
    }

    private QuizView toQuizView(Quiz quiz) {
        List<QuizQuestionView> questions = quiz.getQuestions().stream()
                .map(q -> QuizQuestionView.builder()
                        .questionId(q.getQuestionId())
                        .questionText(q.getQuestionText())
                        .optionA(q.getOptionA())
                        .optionB(q.getOptionB())
                        .optionC(q.getOptionC())
                        .optionD(q.getOptionD())
                        .build())
                .toList();

        return QuizView.builder()
                .quizId(quiz.getQuizId())
                .courseName(quiz.getCourseName())
                .generatedAt(quiz.getGeneratedAt())
                .score(quiz.getScore())
                .takenAt(quiz.getTakenAt())
                .questions(questions)
                .build();
    }
}
