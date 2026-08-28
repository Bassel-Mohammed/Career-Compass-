import { useState } from 'react';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { TextField } from '../../components/TextField';
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  PrerequisiteState,
  Skeleton,
} from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as consultationsApi from '../../api/consultations';
import { dayName, formatDateTime, toLocalDateTime } from '../../api/format';
import { fieldErrorsFor, messageFor, prerequisiteFor } from '../../api/errors';
import type {
  AppointmentStatus,
  AvailabilitySlotResponse,
  MentorSummaryResponse,
} from '../../types';

/** The soonest sensible default: tomorrow at 10:00, in the student's own timezone. */
function defaultSlot(): string {
  const when = new Date();
  when.setDate(when.getDate() + 1);
  when.setHours(10, 0, 0, 0);
  // datetime-local wants "YYYY-MM-DDTHH:mm" — the same shape minus the seconds.
  return toLocalDateTime(when).slice(0, 16);
}

/** "HH:mm:ss" or "HH:mm" as minutes past midnight, for comparing against a picked time. */
function minutesOfDay(time: string): number {
  const [h, m] = time.split(':');
  return Number(h) * 60 + Number(m);
}

/**
 * Does `when` fall inside one of the mentor's published slots?
 *
 * The server enforces this too — this is only so the student finds out before sending the
 * request rather than after. End is exclusive, matching the server, so a 09:00–12:00 slot
 * offers 09:00 through 11:59 but not 12:00 itself.
 */
function isWithinAvailability(when: Date, slots: AvailabilitySlotResponse[]): boolean {
  // JS getDay() is 0=Sunday..6=Saturday; the API uses 1=Monday..7=Sunday.
  const apiDay = when.getDay() === 0 ? 7 : when.getDay();
  const minutes = when.getHours() * 60 + when.getMinutes();
  return slots.some(
    (slot) =>
      slot.dayOfWeek === apiDay &&
      minutes >= minutesOfDay(slot.startTime) &&
      minutes < minutesOfDay(slot.endTime),
  );
}

/** "Mon 09:00–12:00", the shape the mentor entered it in. */
function describeSlot(slot: AvailabilitySlotResponse): string {
  return `${dayName(slot.dayOfWeek).slice(0, 3)} ${slot.startTime.slice(0, 5)}–${slot.endTime.slice(0, 5)}`;
}

const STATUS_TONE: Record<AppointmentStatus, string> = {
  Requested: 'badge--moderate',
  Accepted: 'badge--strong',
  Rejected: 'badge--weak',
  Completed: 'badge--unknown',
};

/**
 * FR-JS-24 and FR-JS-25.
 *
 * Mentors are filtered server-side to the student's own study field and to those currently
 * active for consulting, so this list is often short — and legitimately empty in any
 * environment where no mentor accounts exist.
 */
export function MentorsPage() {
  const { session } = useAuth();
  const token = session!.token;

  const mentors = useAsync(() => consultationsApi.listMentors(token), [token]);
  const appointments = useAsync(() => consultationsApi.listAppointments(token), [token]);
  const book = useAction(consultationsApi.bookAppointment);

  const [booking, setBooking] = useState<MentorSummaryResponse | null>(null);
  const [when, setWhen] = useState(defaultSlot);

  const prereq = prerequisiteFor(mentors.error, 'JOB_SEEKER');
  const errors = fieldErrorsFor(book.error);

  /**
   * Why the picked time would be refused, or undefined when it is fine. Checked here as well
   * as on the server so the student is told before sending, not after — the datetime-local
   * field itself cannot express "Mondays 9–12 only".
   */
  const outsideAvailability =
    booking && !isWithinAvailability(new Date(when), booking.availability ?? [])
      ? 'Outside this mentor’s published times. Pick a slot listed below.'
      : undefined;

  async function handleBook() {
    if (!booking) return;
    const made = await book.run(token, {
      expertId: booking.expertId,
      // A zone-free local date-time. `new Date(when).toISOString()` would append a Z and
      // be rejected by the backend's LocalDateTime binding.
      appointmentDate: toLocalDateTime(new Date(when)),
    });
    if (made) {
      setBooking(null);
      appointments.reload();
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Mentors"
        lede="Experienced people in your own study field who are open to a consultation. You request a time; they accept or decline."
      />

      {prereq && <PrerequisiteState to={prereq.to} message={prereq.message} />}
      {mentors.loading && <Skeleton rows={3} />}
      {!mentors.loading && mentors.failed && !prereq && (
        <ErrorState message={messageFor(mentors.error)} onRetry={mentors.reload} />
      )}

      {!mentors.loading && !prereq && !mentors.failed && (
        <>
          {(mentors.data?.length ?? 0) === 0 ? (
            <EmptyState
              title="No mentors in your field yet"
              body="Nobody in your study field is currently available for consultations. This list fills as mentors are added and mark themselves active."
            />
          ) : (
            <ul className="grid list-reset">
              {mentors.data!.map((mentor) => (
                <Card as="li" key={mentor.expertId} className="mentor">
                  <h3 className="mentor__name">
                    {mentor.firstName} {mentor.lastName}
                  </h3>
                  <p className="mentor__meta">
                    {mentor.studyFieldName ?? 'Field not stated'} · in the field since{' '}
                    {mentor.fieldStartingYear}
                  </p>
                  {(mentor.matchScore !== undefined && mentor.matchScore > 0) && (
                    <div className="mentor__match">
                      <strong>Match Score: {mentor.matchScore.toFixed(0)}%</strong> 
                      <span className="cell__quiet"> (Addresses {mentor.gapsAddressed} gap{mentor.gapsAddressed !== 1 && 's'})</span>
                      <p className="cell__quiet">{mentor.matchReason}</p>
                    </div>
                  )}

                  {(mentor.availability?.length ?? 0) > 0 ? (
                    <p className="cell__quiet">
                      Available: {mentor.availability!.map(describeSlot).join(', ')}
                    </p>
                  ) : (
                    <p className="cell__quiet">
                      Has not published a schedule yet, so they cannot be booked.
                    </p>
                  )}

                  <button
                    type="button"
                    className="button button--secondary button--small button--auto"
                    onClick={() => {
                      setBooking(mentor);
                      book.clearError();
                    }}
                    disabled={(mentor.availability?.length ?? 0) === 0}
                  >
                    Request a session
                  </button>
                </Card>
              ))}
            </ul>
          )}

          {booking && (
            <Card className="booking">
              <h2 className="section__title">
                Request a session with {booking.firstName} {booking.lastName}
              </h2>
              {book.failed && <Banner message={messageFor(book.error)} />}
              <div className="form">
                <TextField
                  label="When"
                  type="datetime-local"
                  value={when}
                  onChange={(e) => setWhen(e.target.value)}
                  error={errors.appointmentDate ?? outsideAvailability}
                  hint={`Their published times: ${(booking.availability ?? []).map(describeSlot).join(', ')}. The mentor still has to accept before it is confirmed.`}
                  disabled={book.running}
                />
                <div className="actions">
                  <button
                    type="button"
                    className="button button--primary button--auto"
                    onClick={() => void handleBook()}
                    disabled={book.running || outsideAvailability !== undefined}
                  >
                    {book.running ? 'Requesting…' : 'Send request'}
                  </button>
                  <button
                    type="button"
                    className="button button--secondary button--auto"
                    onClick={() => setBooking(null)}
                    disabled={book.running}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </Card>
          )}

          <section>
            <h2 className="section__title">
              Your requests
              {appointments.data && (
                <span className="section__count">{appointments.data.length}</span>
              )}
            </h2>
            {appointments.loading && <Skeleton rows={2} />}
            {!appointments.loading && (appointments.data?.length ?? 0) === 0 && (
              <Card>
                <p className="cell__quiet">You have not requested a session yet.</p>
              </Card>
            )}
            {!appointments.loading && (appointments.data?.length ?? 0) > 0 && (
              <ul className="stack list-reset">
                {appointments.data!.map((appointment) => (
                  <Card as="li" key={appointment.appointmentId} className="appointment">
                    <div>
                      <strong>{appointment.expertName}</strong>
                      <p className="cell__quiet">{formatDateTime(appointment.appointmentDate)}</p>
                    </div>
                    <span className={`badge ${STATUS_TONE[appointment.statusName] ?? 'badge--unknown'}`}>
                      {appointment.statusName}
                    </span>
                    {appointment.feedback && (
                      <p className="appointment__note">
                        <strong>Feedback:</strong> {appointment.feedback}
                      </p>
                    )}
                    {appointment.sessionNotes && (
                      <p className="appointment__note">
                        <strong>Notes:</strong> {appointment.sessionNotes}
                      </p>
                    )}
                  </Card>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </AppShell>
  );
}
