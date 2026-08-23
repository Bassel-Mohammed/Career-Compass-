package com.careercompass.controller;

import com.careercompass.dto.request.GenerateQuizRequest;
import com.careercompass.dto.request.SubmitQuizRequest;
import com.careercompass.dto.response.QuizResultResponse;
import com.careercompass.dto.response.QuizView;
import com.careercompass.security.userdetails.CurrentUser;
import com.careercompass.security.userdetails.UserPrincipal;
import com.careercompass.service.QuizService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Job Seeker quiz endpoints (FR-JS-17/18/19). Same `/api/job-seekers/me` prefix and
 * `@CurrentUser` pattern as the other job-seeker controllers. Ownership of a specific quiz
 * (not just "some job seeker") is enforced in QuizService, same pattern as JobService's job
 * ownership check (Increment 8).
 */
@RestController
@RequestMapping("/api/job-seekers/me/quizzes")
@RequiredArgsConstructor
public class QuizController {

    private final QuizService quizService;

    @PostMapping
    public ResponseEntity<QuizView> generateQuiz(@CurrentUser UserPrincipal principal,
                                                   @Valid @RequestBody GenerateQuizRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(quizService.generateQuiz(principal.getUserId(), request));
    }

    @GetMapping("/{quizId}")
    public ResponseEntity<QuizView> getQuiz(@CurrentUser UserPrincipal principal,
                                              @PathVariable Integer quizId) {
        return ResponseEntity.ok(quizService.getQuiz(principal.getUserId(), quizId));
    }

    @PostMapping("/{quizId}/submit")
    public ResponseEntity<QuizResultResponse> submitQuiz(@CurrentUser UserPrincipal principal,
                                                            @PathVariable Integer quizId,
                                                            @Valid @RequestBody SubmitQuizRequest request) {
        return ResponseEntity.ok(quizService.submitQuiz(principal.getUserId(), quizId, request));
    }
}
