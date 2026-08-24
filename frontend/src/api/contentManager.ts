import { request } from './client';
import type {
  ContentManagerResponse,
  LearningOutcomeResponse,
  SelectStudyFieldRequest,
} from '../types';

const PATH = '/api/content-managers/me';

/** PDF only, matching the backend's cap. */
export const MAX_OUTCOME_BYTES = 10 * 1024 * 1024;

/**
 * FR-CM-06. The signed-in content manager's own account.
 *
 * `studyFieldId` and `studyFieldName` are absent until FR-CM-05 has been satisfied — the
 * backend omits null fields entirely — so their absence is how the UI knows a field has not
 * been chosen yet.
 */
export function getProfile(token: string): Promise<ContentManagerResponse> {
  return request<ContentManagerResponse>(PATH, { token });
}

/**
 * FR-CM-05. A hard precondition for uploading: without a study field the upload call
 * answers PREREQUISITE_NOT_MET.
 */
export function selectStudyField(
  token: string,
  body: SelectStudyFieldRequest,
): Promise<ContentManagerResponse> {
  return request<ContentManagerResponse>(`${PATH}/study-field`, { method: 'PUT', token, body });
}

/** FR-CM-04. Multipart, not JSON: `courseName`, optional `description`, and `file`. */
export function uploadLearningOutcome(
  token: string,
  input: { courseName: string; description?: string; file: File },
): Promise<LearningOutcomeResponse> {
  const form = new FormData();
  form.append('courseName', input.courseName);
  if (input.description) form.append('description', input.description);
  form.append('file', input.file);
  return request<LearningOutcomeResponse>(`${PATH}/learning-outcomes`, {
    method: 'POST',
    token,
    body: form,
  });
}

export function listLearningOutcomes(token: string): Promise<LearningOutcomeResponse[]> {
  return request<LearningOutcomeResponse[]>(`${PATH}/learning-outcomes`, { token });
}

/**
 * Deletes the raw PDF from disk once it is no longer needed (NFR-PRIV-03) — the row and
 * its extracted metadata are kept, and come back with `deletedFromDisk: true`. This is
 * "delete the file", not "delete the outcome", and it returns the updated row rather than 204.
 */
export function deleteOutcomeFile(
  token: string,
  outcomeId: number,
): Promise<LearningOutcomeResponse> {
  return request<LearningOutcomeResponse>(`${PATH}/learning-outcomes/${outcomeId}/file`, {
    method: 'DELETE',
    token,
  });
}
