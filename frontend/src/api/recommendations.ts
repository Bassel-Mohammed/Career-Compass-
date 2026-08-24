import { AI_TIMEOUT_MS, request } from './client';
import type { CourseRecommendationItem } from '../types';

const PATH = '/api/job-seekers/me/course-recommendations';

/**
 * FR-JS-15/16. Regenerate from the student's current weak skills, replacing whatever was
 * stored before. **Takes no request body** — the weak skills, career path and quiz evidence
 * are all derived server-side.
 *
 * This is the only call that returns `targetedSkillName` and `explanation`; the stored rows
 * have no columns for them, so {@link listRecommendations} returns them absent.
 */
export function generateRecommendations(token: string): Promise<CourseRecommendationItem[]> {
  return request<CourseRecommendationItem[]>(`${PATH}/generate`, {
    method: 'POST',
    token,
    timeoutMs: AI_TIMEOUT_MS.recommendations,
  });
}

/** Previously generated rows. `targetedSkillName` and `explanation` come back absent. */
export function listRecommendations(token: string): Promise<CourseRecommendationItem[]> {
  return request<CourseRecommendationItem[]>(PATH, { token });
}
