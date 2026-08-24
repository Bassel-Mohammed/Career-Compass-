import { AI_TIMEOUT_MS, request } from './client';
import type { JobMatchResult } from '../types';

/**
 * FR-JS-23. Recomputed fresh on every call, sorted by score descending.
 *
 * ⚠️ **This capability is descoped for the current release.** There is no job-match
 * operation in the AI contract at all. With a real AI service the backend answers
 * **501 AI_CAPABILITY_NOT_IN_SCOPE**; only the mock client returns numbers, and its
 * scores are a placeholder heuristic, not a match. Treat a 501 here as an explained
 * product state, not an outage — see {@link isDescoped}.
 *
 * Slow by construction: the backend makes one AI call per (seeker, job) pair.
 */
export function getJobMatches(token: string): Promise<JobMatchResult[]> {
  return request<JobMatchResult[]>('/api/job-seekers/me/job-matches', {
    token,
    timeoutMs: AI_TIMEOUT_MS.jobMatches,
  });
}

/** True when the backend says the capability is out of scope rather than broken. */
export function isDescoped(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as { code: unknown }).code === 'AI_CAPABILITY_NOT_IN_SCOPE'
  );
}

/**
 * Whether a result came from the mock client. Every mock string is prefixed literally,
 * so this doubles as a "you are not looking at real scores" check for the UI badge.
 */
export function isMockText(text: string | undefined): boolean {
  return text?.includes('[MOCK]') ?? false;
}
