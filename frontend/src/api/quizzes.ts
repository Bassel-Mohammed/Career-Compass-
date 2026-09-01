import { AI_TIMEOUT_MS, request } from './client';
import type { GenerateQuizRequest, QuizResultResponse, QuizView, SubmitQuizRequest } from '../types';

const PATH = '/api/job-seekers/me/quizzes';

/**
 * FR-JS-17. `skillId` must be the dashboard's `canonicalSkillId` (a string), not the
 * numeric `skillId` — which the dashboard never even populates.
 *
 * The quiz can come back with fewer questions than requested: the backend validates that
 * each has exactly one correct option and drops the ones that do not, rather than trusting
 * the model's output (NFR-AI-07).
 */
export function generateQuiz(token: string, body: GenerateQuizRequest): Promise<QuizView> {
  return request<QuizView>(PATH, {
    method: 'POST',
    token,
    body,
    timeoutMs: AI_TIMEOUT_MS.quiz,
  });
}

/** FR-JS-18. The answer key is not included. */
export function getQuiz(token: string, quizId: number): Promise<QuizView> {
  return request<QuizView>(`${PATH}/${quizId}`, { token });
}

/**
 * FR-JS-19/20/21. Grades, persists, and recomputes the dashboard — which is embedded in
 * the response, so there is no need to refetch it.
 *
 * Single-submit: a second attempt returns PREREQUISITE_NOT_MET, not a fresh score.
 * `selectedOption` is a letter A–D. Sending a zero-based index is a validation failure.
 */
export function submitQuiz(
  token: string,
  quizId: number,
  body: SubmitQuizRequest,
): Promise<QuizResultResponse> {
  return request<QuizResultResponse>(`${PATH}/${quizId}/submit`, {
    method: 'POST',
    token,
    body,
    timeoutMs: AI_TIMEOUT_MS.quiz,
  });
}
