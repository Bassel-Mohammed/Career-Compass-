/**
 * Formatting at the API boundary. Everything here exists because a value crosses
 * between the Java DTOs and the browser, and the two disagree about its shape.
 */

/**
 * A `LocalDateTime` the Java backend will accept: `"2026-09-01T14:30:00"`.
 *
 * Spring binds `LocalDateTime` with no zone and no offset. `Date.toISOString()`
 * returns `"2026-09-01T11:30:00.000Z"` — the trailing `Z` makes it an `Instant`,
 * which fails to bind and comes back as a 400 naming a field the user filled in
 * correctly. Build the string from the local calendar fields instead, so what the
 * user picked in their own timezone is what gets sent.
 *
 * Note the consequence: `@Future` is then evaluated against the SERVER's clock. A
 * time that is minutes away in the user's timezone can be rejected as past.
 */
export function toLocalDateTime(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

/** Parse a backend `LocalDateTime` as a local instant (no zone conversion). */
export function fromLocalDateTime(value: string): Date {
  return new Date(value);
}

/** `"09:00:00"` — the `LocalTime` shape availability slots use. */
export function toLocalTime(hhmm: string): string {
  return hhmm.length === 5 ? `${hhmm}:00` : hhmm;
}

/** `"09:00:00"` back to the `"09:00"` an `<input type="time">` expects. */
export function fromLocalTime(value: string): string {
  return value.slice(0, 5);
}

/**
 * A 0..100 score for display. Everything the API returns is already a percentage —
 * the backend converts the AI's 0.0..1.0 in exactly one place — so this only rounds.
 * The mock client can return many decimal places, hence the rounding.
 */
export function formatPercent(score: number | undefined, digits = 0): string {
  if (score === undefined) return '—';
  return `${score.toFixed(digits)}%`;
}

/**
 * ⚠️ The exception. `ExtractedCourseItem.confidence` is the single field in the public
 * API still on the AI's native 0.0..1.0 scale — it bypasses the backend's `toPercent()`.
 * Passing it to {@link formatPercent} renders "0.82%" instead of "82%".
 *
 * A missing value is not zero confidence: the AI returns a per-row probability only
 * sometimes, and absence means "not reported", so it renders as an em dash.
 */
export function formatConfidence(confidence: number | undefined): string {
  if (confidence === undefined) return '—';
  return `${Math.round(confidence * 100)}%`;
}

/** A `LocalDateTime` string as a readable date. */
export function formatDate(value: string): string {
  return fromLocalDateTime(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/** A `LocalDateTime` string as a readable date and time. */
export function formatDateTime(value: string): string {
  return fromLocalDateTime(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

/** Monday-first, matching the backend's 1..7 `dayOfWeek`. */
export const DAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

/** `dayOfWeek` is 1..7, so index with `day - 1`. Off-by-one here mislabels every slot. */
export function dayName(dayOfWeek: number): string {
  return DAY_NAMES[dayOfWeek - 1] ?? `Day ${dayOfWeek}`;
}

/** The letter the API expects for a zero-based radio index. Never send the index. */
export const OPTION_LETTERS = ['A', 'B', 'C', 'D'] as const;
