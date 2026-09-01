import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { AuthContext, type AuthContextValue } from './AuthContext';
import { clearSession, loadSession, saveSession, toSession } from './session';
import * as authApi from '../api/auth';
import type { AuthResponse, Session } from '../types';

const SESSION_WARNING_MS = 60_000;
const SESSION_WARNING_TOAST_ID = 'session-expiry-warning';
const SESSION_EXPIRED_TOAST_ID = 'session-expired';
const MAX_TIMER_DELAY_MS = 2_147_483_647;

export function AuthProvider({ children }: { children: ReactNode }) {
  // Read storage once, during the first render, so a reload never flashes the
  // signed-out UI before restoring a session that was there all along.
  const [session, setSession] = useState<Session | null>(() => loadSession());

  const signIn = useCallback((auth: AuthResponse): Session => {
    const next = toSession(auth);
    saveSession(next);
    setSession(next);
    return next;
  }, []);

  const signOut = useCallback(async () => {
    const token = session?.token;
    // Drop it locally first. If the network call fails the user is still signed out
    // here, which is the outcome they asked for; the token then simply expires.
    clearSession();
    setSession(null);
    if (token) {
      try {
        await authApi.logout(token);
      } catch {
        /* already signed out locally */
      }
    }
  }, [session]);

  // Warn one minute before the fixed token lifetime ends, then remove the session at
  // the exact expiry instant. ProtectedRoute will immediately return the user to login.
  useEffect(() => {
    if (!session) return;

    const msUntilExpiry = Math.max(0, session.expiresAt - Date.now());
    const warningDelay = Math.min(
      Math.max(0, msUntilExpiry - SESSION_WARNING_MS),
      MAX_TIMER_DELAY_MS,
    );
    const expiryDelay = Math.min(msUntilExpiry, MAX_TIMER_DELAY_MS);

    const warningTimer = window.setTimeout(() => {
      toast.warning('You will be signed out automatically in 1 minute. Save your work now.', {
        id: SESSION_WARNING_TOAST_ID,
        duration: SESSION_WARNING_MS,
      });
    }, warningDelay);

    const expiryTimer = window.setTimeout(() => {
      toast.dismiss(SESSION_WARNING_TOAST_ID);
      clearSession();
      setSession(null);
      toast.error('Your 30-minute session has ended. Please sign in again.', {
        id: SESSION_EXPIRED_TOAST_ID,
      });
    }, expiryDelay);

    return () => {
      window.clearTimeout(warningTimer);
      window.clearTimeout(expiryTimer);
      toast.dismiss(SESSION_WARNING_TOAST_ID);
    };
  }, [session]);

  const value = useMemo<AuthContextValue>(
    () => ({ session, signIn, signOut }),
    [session, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
