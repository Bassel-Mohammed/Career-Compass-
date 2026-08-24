import { request } from './client';
import type {
  CareerPathResponse,
  ContentManagerResponse,
  CreateCareerPathRequest,
  CreateContentManagerRequest,
  CreateExpertRequest,
  CreateStudyFieldRequest,
  CreateUniversityRequest,
  ExpertResponse,
  StudyFieldResponse,
  UniversityResponse,
  UpdateCareerPathRequest,
  UpdateContentManagerRequest,
} from '../types';

const PATH = '/api/admin';

/*
 * Writes only. The matching GET lists live in reference.ts, which any signed-in actor can
 * read; the admin-scoped GETs return the same rows and exist only for this section's own use.
 *
 * Bootstrap order matters and the UI should reflect it:
 *   universities -> study fields -> career paths -> content managers and mentors.
 * A content manager cannot be created without a university, and a career path cannot be
 * created without at least one study field.
 */

// --- Content managers (FR-SA-02..06) ---------------------------------------

export function listContentManagers(token: string): Promise<ContentManagerResponse[]> {
  return request<ContentManagerResponse[]>(`${PATH}/content-managers`, { token });
}

export function createContentManager(
  token: string,
  body: CreateContentManagerRequest,
): Promise<ContentManagerResponse> {
  return request<ContentManagerResponse>(`${PATH}/content-managers`, {
    method: 'POST',
    token,
    body,
  });
}

export function updateContentManager(
  token: string,
  id: number,
  body: UpdateContentManagerRequest,
): Promise<ContentManagerResponse> {
  return request<ContentManagerResponse>(`${PATH}/content-managers/${id}`, {
    method: 'PUT',
    token,
    body,
  });
}

/** FR-SA-05/06. A deactivated content manager cannot sign in. */
export function setContentManagerActive(
  token: string,
  id: number,
  active: boolean,
): Promise<ContentManagerResponse> {
  const action = active ? 'activate' : 'deactivate';
  return request<ContentManagerResponse>(`${PATH}/content-managers/${id}/${action}`, {
    method: 'PATCH',
    token,
  });
}

// --- Mentors ----------------------------------------------------------------

/**
 * The only way a mentor account comes into being — there is no self-registration.
 * New mentors start Inactive and must opt in themselves before students can see them.
 * There is no list or delete endpoint for mentors.
 */
export function createExpert(token: string, body: CreateExpertRequest): Promise<ExpertResponse> {
  return request<ExpertResponse>(`${PATH}/experts`, { method: 'POST', token, body });
}

// --- Reference data (FR-SA-07..10) ------------------------------------------

export function createStudyField(
  token: string,
  body: CreateStudyFieldRequest,
): Promise<StudyFieldResponse> {
  return request<StudyFieldResponse>(`${PATH}/study-fields`, { method: 'POST', token, body });
}

export function createUniversity(
  token: string,
  body: CreateUniversityRequest,
): Promise<UniversityResponse> {
  return request<UniversityResponse>(`${PATH}/universities`, { method: 'POST', token, body });
}

export function createCareerPath(
  token: string,
  body: CreateCareerPathRequest,
): Promise<CareerPathResponse> {
  return request<CareerPathResponse>(`${PATH}/career-paths`, { method: 'POST', token, body });
}

/** `studyFieldIds`, if given, replaces the whole set. Send the complete list. */
export function updateCareerPath(
  token: string,
  id: number,
  body: UpdateCareerPathRequest,
): Promise<CareerPathResponse> {
  return request<CareerPathResponse>(`${PATH}/career-paths/${id}`, { method: 'PUT', token, body });
}

export function deleteCareerPath(token: string, id: number): Promise<void> {
  return request<void>(`${PATH}/career-paths/${id}`, { method: 'DELETE', token });
}
