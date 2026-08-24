import { request } from './client';
import type { CareerPathResponse, StudyFieldResponse, UniversityResponse } from '../types';

/**
 * Shared lookup lists. Any signed-in actor may read these — see ReferenceDataController.
 * Creating and editing them stays on /api/admin/** (see admin.ts).
 */

export function listStudyFields(token: string): Promise<StudyFieldResponse[]> {
  return request<StudyFieldResponse[]>('/api/reference/study-fields', { token });
}

export function listCareerPaths(token: string): Promise<CareerPathResponse[]> {
  return request<CareerPathResponse[]>('/api/reference/career-paths', { token });
}

export function listUniversities(token: string): Promise<UniversityResponse[]> {
  return request<UniversityResponse[]>('/api/reference/universities', { token });
}

/**
 * The paths open to a given study field (FR-JS-09: "related to their studied field").
 * Filtered here rather than server-side because every path already carries its fields.
 * An unset study field means we cannot narrow anything, so show them all rather than
 * showing nothing.
 */
export function pathsForStudyField(
  paths: CareerPathResponse[],
  studyFieldId: number | undefined,
): CareerPathResponse[] {
  if (studyFieldId === undefined) return paths;
  const matching = paths.filter((p) => p.studyFields.some((f) => f.studyFieldId === studyFieldId));
  // A field nobody has linked a path to would otherwise dead-end the student.
  return matching.length > 0 ? matching : paths;
}
