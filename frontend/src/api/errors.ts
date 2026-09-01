import { ApiError, NetworkError, TimeoutError } from './client';
import type { Role } from '../types';

/**
 * Turning a backend failure into something the screen can act on (NFR-USE-03: every error
 * states how to recover).
 */

/** Where a missing prerequisite should send the user, and what to tell them when they land. */
export interface Prerequisite {
  to: string;
  message: string;
}

/**
 * The backend answers PREREQUISITE_NOT_MET (400) when an earlier step in the journey has
 * not happened — no career path chosen, no transcript confirmed, no study field set. The
 * message names the step, so it is matched here rather than parsed for a code the backend
 * does not send.
 *
 * Rendering these as a plain red banner would be a dead end: the user is told what is
 * missing but not taken to the place that fixes it. Each one maps to a route instead.
 *
 * `role` is required rather than defaulted because two actors hit the *same* study-field
 * message for different reasons and must be sent to different screens — a content manager
 * routed to the job seeker's `/setup` lands on a page their role cannot even load. Defaulting
 * would make that failure silent the next time an actor is added.
 */
export function prerequisiteFor(error: unknown, role: Role): Prerequisite | null {
  if (!(error instanceof ApiError) || error.code !== 'PREREQUISITE_NOT_MET') return null;

  const text = error.message.toLowerCase();

  if (text.includes('career path')) {
    return {
      to: '/setup',
      message: 'Choose the career path you want to be measured against first.',
    };
  }
  if (text.includes('study field')) {
    // Same backend message, different owners: the student needs one to be matched with
    // mentors, the content manager needs one before anything they upload has a home.
    return role === 'CONTENT_MANAGER'
      ? {
          to: '/content/profile',
          message:
            'Choose the study field you teach first — uploads are filed under your university and field.',
        }
      : {
          to: '/setup',
          message: 'Set your study field first — mentors are matched within your own field.',
        };
  }
  if (text.includes('transcript')) {
    return {
      to: '/transcript',
      message: 'Upload and confirm your transcript first — everything here is built from it.',
    };
  }
  // Something new: still a prerequisite, but not one this build knows how to route.
  return null;
}

/** A quiz that has already been submitted comes back as a prerequisite failure too. */
export function isAlreadySubmitted(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.code === 'PREREQUISITE_NOT_MET' &&
    error.message.toLowerCase().includes('already been submitted')
  );
}

/** The AI service is unreachable, slow, or answered with something invalid. */
export function isAiFailure(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 502 && error.status <= 504;
}

/** The capability is deliberately not in this release — not an outage. */
export function isNotInScope(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'AI_CAPABILITY_NOT_IN_SCOPE';
}

/** The session is gone. The auth layer handles the redirect; screens just stop rendering. */
export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/**
 * One human-readable sentence for any failure, preferring the server's own wording —
 * it is written to be non-technical, unlike anything we would invent from a status code.
 */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (isAiFailure(error)) {
      return `${error.message} The analysis service may still be starting up.`;
    }
    return error.message;
  }
  if (error instanceof TimeoutError || error instanceof NetworkError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

/**
 * The same as {@link messageFor}, but safe on screens whose 502s are disk faults rather than
 * AI faults.
 *
 * `FileStorageService` throws `IllegalStateException` for any file I/O failure, and
 * `GlobalExceptionHandler` maps *every* `IllegalStateException` to 502
 * `AI_SERVICE_RESPONSE_INVALID`. Two things go wrong if such an error is rendered normally:
 * the user is told the analysis service is starting up when nothing analysed anything, and the
 * delete path's message embeds the **absolute server filesystem path**, which should never
 * reach a browser.
 */
export function storageMessageFor(error: unknown): string {
  if (isAiFailure(error)) {
    return 'The file could not be saved or removed on the server. Please try again, and tell an administrator if it keeps happening.';
  }
  return messageFor(error);
}

/** Field-level messages keyed by form field, for attaching to inputs. */
export function fieldErrorsFor(error: unknown): Record<string, string> {
  return error instanceof ApiError ? error.byField() : {};
}
