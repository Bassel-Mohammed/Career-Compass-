import { request } from './client';
import type { AppointmentResponse, BookAppointmentRequest, MentorSummaryResponse } from '../types';

const PATH = '/api/job-seekers/me';

/**
 * FR-JS-24. Mentors in the student's own study field who are currently Active for
 * consulting. Requires the study field to be set (PREREQUISITE_NOT_MET otherwise).
 *
 * An empty list is the normal state outside the dev profile — the mentor catalogue has
 * no rows in any other environment.
 */
export function listMentors(token: string): Promise<MentorSummaryResponse[]> {
  return request<MentorSummaryResponse[]>(`${PATH}/mentors`, { token });
}

/**
 * FR-JS-25. Always created as "Requested"; the mentor then accepts or rejects.
 * `appointmentDate` must be a zone-free local date-time — use `toLocalDateTime()`.
 * No availability or double-booking check happens here.
 */
export function bookAppointment(
  token: string,
  body: BookAppointmentRequest,
): Promise<AppointmentResponse> {
  return request<AppointmentResponse>(`${PATH}/appointments`, { method: 'POST', token, body });
}

/** The student's own bookings, newest first. */
export function listAppointments(token: string): Promise<AppointmentResponse[]> {
  return request<AppointmentResponse[]>(`${PATH}/appointments`, { token });
}
