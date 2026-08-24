import { AI_TIMEOUT_MS, request } from './client';
import type {
  AppointmentResponse,
  AvailabilitySlotResponse,
  ConsultationOutcomeRequest,
  CourseRecommendationItem,
  ExpertResponse,
  SkillDashboardResponse,
  UpdateAvailabilityRequest,
} from '../types';

const PATH = '/api/experts/me';

/** Read-only — there is no PUT. A mentor's own name and field are set by an administrator. */
export function getProfile(token: string): Promise<ExpertResponse> {
  return request<ExpertResponse>(PATH, { token });
}

/**
 * FR-EX-02. Two distinct URLs rather than a body, so the toggle picks a path.
 * Only "Active" mentors appear to students browsing their field.
 */
export function setActive(token: string, active: boolean): Promise<ExpertResponse> {
  const action = active ? 'activate' : 'deactivate';
  return request<ExpertResponse>(`${PATH}/status/${action}`, { method: 'PATCH', token });
}

/**
 * FR-EX-06. A **full replace** of the weekly schedule — the server deletes every slot and
 * re-inserts what it is given. Always send the complete week; sending one changed day wipes
 * the rest. `dayOfWeek` is 1..7, not 0..6.
 */
export function updateAvailability(
  token: string,
  body: UpdateAvailabilityRequest,
): Promise<AvailabilitySlotResponse[]> {
  return request<AvailabilitySlotResponse[]>(`${PATH}/availability`, {
    method: 'PUT',
    token,
    body,
  });
}

/**
 * FR-EX-05. Filtered on date alone, not status — so this includes Requested and Rejected
 * appointments and overlaps {@link listHistory}. Filter by `statusName` in the UI.
 */
export function listScheduled(token: string): Promise<AppointmentResponse[]> {
  return request<AppointmentResponse[]>(`${PATH}/sessions/scheduled`, { token });
}

/** FR-EX-12. Every appointment for this mentor, newest first. */
export function listHistory(token: string): Promise<AppointmentResponse[]> {
  return request<AppointmentResponse[]>(`${PATH}/sessions/history`, { token });
}

/** FR-EX-03 / FR-EX-04. */
export function respondToRequest(
  token: string,
  appointmentId: number,
  accept: boolean,
): Promise<AppointmentResponse> {
  const action = accept ? 'accept' : 'reject';
  return request<AppointmentResponse>(`${PATH}/appointments/${appointmentId}/${action}`, {
    method: 'PATCH',
    token,
  });
}

/**
 * FR-EX-09/10/11. Both fields optional; omitting one leaves it unchanged.
 * `feedback` carries the readiness evaluation as well — the schema has no separate column.
 */
export function recordOutcome(
  token: string,
  appointmentId: number,
  body: ConsultationOutcomeRequest,
): Promise<AppointmentResponse> {
  return request<AppointmentResponse>(`${PATH}/appointments/${appointmentId}/outcome`, {
    method: 'PATCH',
    token,
    body,
  });
}

/**
 * FR-EX-07. Gated on an existing booking between this mentor and that student — otherwise
 * 403. Recomputed live, so it costs an AI round trip and can raise the student's own
 * prerequisite errors if they never confirmed a transcript.
 */
export function getJobSeekerDashboard(
  token: string,
  jobseekerId: number,
): Promise<SkillDashboardResponse> {
  return request<SkillDashboardResponse>(`${PATH}/job-seekers/${jobseekerId}/skill-dashboard`, {
    token,
    timeoutMs: AI_TIMEOUT_MS.dashboard,
  });
}

/**
 * FR-EX-08. Same gate. Reads stored rows, so `targetedSkillName` and `explanation` are
 * always absent on this screen.
 */
export function getJobSeekerRecommendations(
  token: string,
  jobseekerId: number,
): Promise<CourseRecommendationItem[]> {
  return request<CourseRecommendationItem[]>(
    `${PATH}/job-seekers/${jobseekerId}/course-recommendations`,
    { token },
  );
}
