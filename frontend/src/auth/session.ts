import type { AuthResponse, Session } from '../types';

const STORAGE_KEY = 'careercompass.session';

/**
 * Turn a fresh AuthResponse into the session we keep. `expiresInSeconds` is relative
 * to the moment the server issued the token, so it is resolved to an absolute instant
 * here — a relative lifetime is meaningless once it has been sitting in storage.
 */
export function toSession(auth: AuthResponse): Session {
  return {
    token: auth.token,
    role: auth.role,
    userId: auth.userId,
    email: auth.email,
    expiresAt: Date.now() + auth.expiresInSeconds * 1000,
  };
}

export function isExpired(session: Session): boolean {
  return Date.now() >= session.expiresAt;
}

/**
 * Read the stored session, or null. An expired or unreadable one is discarded rather
 * than returned: presenting a dead token just earns a 401 on the first real request.
 */
export function loadSession(): Session | null {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // Storage disabled (private window, blocked site data).
  }
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Session;
    if (!parsed?.token || !parsed?.role || typeof parsed.expiresAt !== 'number') {
      clearSession();
      return null;
    }
    if (isExpired(parsed)) {
      clearSession();
      return null;
    }
    return parsed;
  } catch {
    clearSession();
    return null;
  }
}

export function saveSession(session: Session): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Not fatal: the session still works for this tab, it just will not survive a reload.
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to clear */
  }
}
