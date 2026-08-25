import { request } from './client';
import type {
  AddDraftSkillRequest,
  ContentManagerResponse,
  DeleteDraftSkillRequest,
  DraftSkillResponse,
  LearningOutcomeResponse,
  PublishLearningOutcomeRequest,
  ReplaceDraftSkillRequest,
  SelectStudyFieldRequest,
  TaxonomySkillSearchResponse,
  UpdateDraftSkillRequest,
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

/**
 * Multipart upload. The qualified course identity is deliberately supplied by the content
 * manager rather than inferred from a filename or from text extracted from the PDF.
 */
export function uploadLearningOutcome(
  token: string,
  input: {
    courseCode: string;
    catalogVersion: string;
    courseName: string;
    description?: string;
    file: File;
  },
): Promise<LearningOutcomeResponse> {
  const form = new FormData();
  form.append('courseCode', input.courseCode);
  form.append('catalogVersion', input.catalogVersion);
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

export function getLearningOutcome(
  token: string,
  outcomeId: number,
): Promise<LearningOutcomeResponse> {
  return request<LearningOutcomeResponse>(`${PATH}/learning-outcomes/${outcomeId}`, { token });
}

/** Small polling resource used while extraction or publication is running. */
export function getExtractionStatus(
  token: string,
  outcomeId: number,
): Promise<LearningOutcomeResponse> {
  return request<LearningOutcomeResponse>(
    `${PATH}/learning-outcomes/${outcomeId}/extraction`,
    { token },
  );
}

export function retryExtraction(
  token: string,
  outcomeId: number,
): Promise<LearningOutcomeResponse> {
  return request<LearningOutcomeResponse>(
    `${PATH}/learning-outcomes/${outcomeId}/extraction/retry`,
    { method: 'POST', token },
  );
}

export function cancelExtraction(
  token: string,
  outcomeId: number,
): Promise<LearningOutcomeResponse> {
  return request<LearningOutcomeResponse>(
    `${PATH}/learning-outcomes/${outcomeId}/extraction`,
    { method: 'DELETE', token },
  );
}

export function listDraftSkills(
  token: string,
  outcomeId: number,
): Promise<DraftSkillResponse[]> {
  return request<DraftSkillResponse[]>(`${PATH}/learning-outcomes/${outcomeId}/skills`, {
    token,
  });
}

export function addDraftSkill(
  token: string,
  outcomeId: number,
  body: AddDraftSkillRequest,
): Promise<DraftSkillResponse> {
  return request<DraftSkillResponse>(`${PATH}/learning-outcomes/${outcomeId}/skills`, {
    method: 'POST',
    token,
    body,
  });
}

export function updateDraftSkill(
  token: string,
  outcomeId: number,
  draftSkillId: number,
  body: UpdateDraftSkillRequest,
): Promise<DraftSkillResponse> {
  return request<DraftSkillResponse>(
    `${PATH}/learning-outcomes/${outcomeId}/skills/${draftSkillId}`,
    { method: 'PATCH', token, body },
  );
}

export function replaceDraftSkill(
  token: string,
  outcomeId: number,
  draftSkillId: number,
  body: ReplaceDraftSkillRequest,
): Promise<DraftSkillResponse> {
  return request<DraftSkillResponse>(
    `${PATH}/learning-outcomes/${outcomeId}/skills/${draftSkillId}/replacement`,
    { method: 'PUT', token, body },
  );
}

export function deleteDraftSkill(
  token: string,
  outcomeId: number,
  draftSkillId: number,
  body: DeleteDraftSkillRequest,
): Promise<DraftSkillResponse> {
  return request<DraftSkillResponse>(
    `${PATH}/learning-outcomes/${outcomeId}/skills/${draftSkillId}`,
    { method: 'DELETE', token, body },
  );
}

export function searchTaxonomySkills(
  token: string,
  query: string,
  limit = 20,
): Promise<TaxonomySkillSearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request<TaxonomySkillSearchResponse>(`${PATH}/skills/search?${params.toString()}`, {
    token,
  });
}

export function publishLearningOutcome(
  token: string,
  outcomeId: number,
  body: PublishLearningOutcomeRequest,
): Promise<LearningOutcomeResponse> {
  return request<LearningOutcomeResponse>(`${PATH}/learning-outcomes/${outcomeId}/publish`, {
    method: 'POST',
    token,
    body,
  });
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
