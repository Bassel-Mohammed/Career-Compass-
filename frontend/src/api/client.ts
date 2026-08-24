import type { ApiErrorResponse, FieldError } from '../types';

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';

/**
 * A failure the API described in its own words. Every error the backend produces —
 * from the security filter chain and from GlobalExceptionHandler alike — arrives as
 * an ApiErrorResponse, so there is exactly one shape to parse.
 */
export class ApiError extends Error {
  readonly status: number;
  /** Machine-readable code: INVALID_CREDENTIALS, EMAIL_ALREADY_EXISTS, VALIDATION_ERROR… */
  readonly code: string;
  readonly fieldErrors: FieldError[];

  constructor(status: number, code: string, message: string, fieldErrors: FieldError[] = []) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }

  /** Field errors keyed by field name, for attaching messages to inputs. */
  byField(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const fe of this.fieldErrors) {
      // Keep the first message per field; Bean Validation can report several.
      if (fe.field && !(fe.field in out)) out[fe.field] = fe.message;
    }
    return out;
  }
}

/** The API is unreachable — server down, wrong port, CORS refusal. Not an ApiError. */
export class NetworkError extends Error {
  constructor() {
    super(
      'Could not reach the CareerCompass server. Check that the backend is running ' +
        `at ${BASE_URL}, then try again.`,
    );
    this.name = 'NetworkError';
  }
}

/**
 * The request outlived its deadline. Distinct from NetworkError because the causes and the
 * advice differ: the server is reachable, it is just still working (or wedged). The AI-backed
 * routes are the realistic source of these.
 */
export class TimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(
      `That took longer than ${Math.round(timeoutMs / 1000)} seconds and was stopped. ` +
        'The AI service may be starting up — try again in a moment.',
    );
    this.name = 'TimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

/**
 * One signal that aborts when any of its inputs does. `AbortSignal.any` exists in modern
 * browsers but not in every environment the tests run in, so fall back to wiring listeners.
 */
function anySignal(...signals: (AbortSignal | undefined)[]): AbortSignal {
  const present = signals.filter((s): s is AbortSignal => s !== undefined);
  if (present.length === 1) return present[0];
  if (typeof AbortSignal.any === 'function') return AbortSignal.any(present);

  const controller = new AbortController();
  for (const s of present) {
    if (s.aborted) {
      controller.abort(s.reason);
      break;
    }
    s.addEventListener('abort', () => controller.abort(s.reason), { once: true });
  }
  return controller.signal;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** JSON body, or a FormData for multipart uploads. */
  body?: unknown;
  /** Bearer token to send. Omit for the public /api/auth routes. */
  token?: string;
  signal?: AbortSignal;
  /**
   * Abort after this many milliseconds. The AI-backed routes are far slower than
   * ordinary CRUD — NFR-PERF-02 allows 30s for transcript processing and NFR-PERF-04
   * 15s for quiz generation — so a single global deadline would either cut those off
   * or let a dead endpoint hang forever. Defaults to {@link DEFAULT_TIMEOUT_MS}.
   */
  timeoutMs?: number;
}

/** Ordinary CRUD. NFR-PERF-01 budgets 2s; this is the give-up point, not the target. */
export const DEFAULT_TIMEOUT_MS = 15_000;

/** Deadlines for the slow AI-backed operations, from the NFR-PERF budgets plus headroom. */
export const AI_TIMEOUT_MS = {
  /** NFR-PERF-02: 30s for a transcript of up to 10 pages. */
  transcript: 45_000,
  /** NFR-PERF-03: 10s for gap analysis, but a cold AI service loads its index first. */
  dashboard: 30_000,
  /** NFR-PERF-05: 5s for retrieval. */
  recommendations: 30_000,
  /** NFR-PERF-04: 15s to generate; submitting also recomputes the dashboard. */
  quiz: 45_000,
  /** Scores one AI call per (seeker, job) pair — deliberately generous. */
  jobMatches: 60_000,
} as const;

/**
 * One request against the Spring Boot API.
 *
 * Returns the parsed body, or `undefined` for 204 — which is what logout answers with.
 * Throws {@link ApiError} for anything the server rejected, {@link NetworkError} if the
 * request never got there.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, token, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const isMultipart = body instanceof FormData;

  const headers: Record<string, string> = { Accept: 'application/json' };
  // Multipart must NOT get an explicit Content-Type: the browser has to set the header
  // itself so it can include the boundary token it generated. Setting it by hand
  // produces a body the server cannot split into parts.
  if (body !== undefined && !isMultipart) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;

  // Combine the caller's cancellation with our deadline: whichever fires first wins.
  const timeout = new AbortController();
  const timer = window.setTimeout(() => timeout.abort(new TimeoutError(timeoutMs)), timeoutMs);
  const composed = anySignal(signal, timeout.signal);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isMultipart ? body : JSON.stringify(body),
      signal: composed,
    });
  } catch (cause) {
    if (timeout.signal.aborted) throw new TimeoutError(timeoutMs);
    // An aborted request is the caller's own doing, not a server failure.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new NetworkError();
  } finally {
    window.clearTimeout(timer);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed: unknown = text ? safeParse(text) : null;

  if (!response.ok) {
    const err = parsed as ApiErrorResponse | null;
    throw new ApiError(
      response.status,
      err?.error ?? 'UNKNOWN',
      err?.message ?? fallbackMessage(response.status),
      err?.fieldErrors ?? [],
    );
  }

  return parsed as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Used only when the server returned an error with no parseable body. */
function fallbackMessage(status: number): string {
  if (status >= 500) return 'The server ran into a problem. Please try again in a moment.';
  return 'That request could not be completed. Please check your details and try again.';
}

export { BASE_URL };
