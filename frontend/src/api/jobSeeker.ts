import { request } from './client';
import type { JobSeekerProfileResponse, UpdateJobSeekerProfileRequest, JobResponse } from '../types';

export interface Page<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  size: number;
  number: number;
}

export function getProfile(token: string): Promise<JobSeekerProfileResponse> {
  return request<JobSeekerProfileResponse>('/api/job-seekers/me', { token });
}

/**
 * Partial update — only the fields present are applied (FR-JS-07, FR-JS-09).
 * This is the only way to set `studyFieldId` and `careerPathId`, both of which gate
 * the transcript, dashboard, recommendations, quizzes and mentor flows.
 */
export function updateProfile(
  token: string,
  body: UpdateJobSeekerProfileRequest,
): Promise<JobSeekerProfileResponse> {
  return request<JobSeekerProfileResponse>('/api/job-seekers/me', { method: 'PUT', token, body });
}

/**
 * FR-JS-08 / NFR-PRIV-02, right to erasure. Cascades academic records, skills, quizzes
 * and matches. Irreversible — never call without an explicit confirmation.
 */
export function deleteProfile(token: string): Promise<void> {
  return request<void>('/api/job-seekers/me', { method: 'DELETE', token });
}

export function listActiveJobs(token: string, page = 0, size = 20): Promise<Page<JobResponse>> {
  return request<Page<JobResponse>>(`/api/job-seekers/me/jobs?page=${page}&size=${size}`, { token });
}
