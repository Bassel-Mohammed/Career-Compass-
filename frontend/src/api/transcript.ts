import { AI_TIMEOUT_MS, request } from './client';
import type {
  ConfirmTranscriptRequest,
  SkillDashboardResponse,
  TranscriptReviewResponse,
} from '../types';

/** PDF only, and the backend rejects anything larger (NFR-PERF-07). */
export const MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024;

/**
 * FR-JS-10. Extract courses and grades for review. **Nothing is persisted** — the
 * student corrects the table and then calls {@link confirmTranscript}.
 * The multipart part must be named `file`.
 */
export function uploadTranscript(token: string, file: File): Promise<TranscriptReviewResponse> {
  const form = new FormData();
  form.append('file', file);
  return request<TranscriptReviewResponse>('/api/job-seekers/me/transcript', {
    method: 'POST',
    token,
    body: form,
    timeoutMs: AI_TIMEOUT_MS.transcript,
  });
}

/**
 * FR-JS-11. Persist the reviewed rows and build the skill vector in one step, returning
 * the first dashboard. Requires a career path to be set already, or the backend answers
 * PREREQUISITE_NOT_MET.
 */
export function confirmTranscript(
  token: string,
  body: ConfirmTranscriptRequest,
): Promise<SkillDashboardResponse> {
  return request<SkillDashboardResponse>('/api/job-seekers/me/transcript/confirm', {
    method: 'POST',
    token,
    body,
    timeoutMs: AI_TIMEOUT_MS.dashboard,
  });
}

/**
 * FR-JS-14/21. Recomputed live on every call from the persisted records — not cached —
 * so it always reflects the latest grades and career path, and always costs an AI round trip.
 */
export function getSkillDashboard(token: string): Promise<SkillDashboardResponse> {
  return request<SkillDashboardResponse>('/api/job-seekers/me/skill-dashboard', {
    token,
    timeoutMs: AI_TIMEOUT_MS.dashboard,
  });
}
