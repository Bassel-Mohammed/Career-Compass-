import { AI_TIMEOUT_MS, request } from './client';
import type {
  CandidateMatchResult,
  EmployerProfileResponse,
  JobPostRequest,
  JobResponse,
  UpdateEmployerProfileRequest,
} from '../types';

const PATH = '/api/employers/me';

export function getProfile(token: string): Promise<EmployerProfileResponse> {
  return request<EmployerProfileResponse>(PATH, { token });
}

/** FR-EMP-06. Partial update. Email and password are deliberately not editable here. */
export function updateProfile(
  token: string,
  body: UpdateEmployerProfileRequest,
): Promise<EmployerProfileResponse> {
  return request<EmployerProfileResponse>(PATH, { method: 'PUT', token, body });
}

/** FR-EMP-10. */
export function listJobs(token: string): Promise<JobResponse[]> {
  return request<JobResponse[]>(`${PATH}/jobs`, { token });
}

/** FR-EMP-07. */
export function createJob(token: string, body: JobPostRequest): Promise<JobResponse> {
  return request<JobResponse>(`${PATH}/jobs`, { method: 'POST', token, body });
}

/** FR-EMP-09. A full replace — send every field, not just the changed ones. */
export function updateJob(
  token: string,
  jobId: number,
  body: JobPostRequest,
): Promise<JobResponse> {
  return request<JobResponse>(`${PATH}/jobs/${jobId}`, { method: 'PUT', token, body });
}

/** FR-EMP-10. Hard delete. */
export function deleteJob(token: string, jobId: number): Promise<void> {
  return request<void>(`${PATH}/jobs/${jobId}`, { method: 'DELETE', token });
}

/**
 * FR-EMP-11/12. Ranked candidates for one posting, capped at 20 with no pagination.
 * Only job seekers who already have a skill profile are scored, so an empty list is a
 * legitimate result rather than an error.
 *
 * ⚠️ Descoped like job matching: with a real AI service this returns 501
 * AI_CAPABILITY_NOT_IN_SCOPE. Only the mock produces scores.
 */
export function listCandidates(token: string, jobId: number): Promise<CandidateMatchResult[]> {
  return request<CandidateMatchResult[]>(`${PATH}/jobs/${jobId}/candidates`, {
    token,
    timeoutMs: AI_TIMEOUT_MS.jobMatches,
  });
}
