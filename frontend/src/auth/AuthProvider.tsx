import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AuthContext, type AuthContextValue } from './AuthContext';
import { clearSession, loadSession, saveSession, toSession } from './session';
import * as authApi from '../api/auth';
import type { AuthResponse, Session } from '../types';

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

  // A token has a fixed lifetime, and the tab may be left open past it. Rather than
  // let the next request fail with a confusing 401, drop the session the moment it dies.
  useEffect(() => {
    if (!session) return;

    // Always go through the timer, even for a session that is already past its expiry:
    // clearing state synchronously inside the effect would start a second render pass
    // for no gain, and a 0 ms timeout lands on the very next tick anyway.
    // setTimeout tops out at a signed 32-bit millisecond delay; a longer-lived token
    // would otherwise wrap around and fire immediately.
    const MAX_DELAY = 2_147_483_647;
    const msLeft = Math.min(Math.max(0, session.expiresAt - Date.now()), MAX_DELAY);

    const timer = window.setTimeout(() => {
      clearSession();
      setSession(null);
    }, msLeft);
    return () => window.clearTimeout(timer);
  }, [session]);

  const value = useMemo<AuthContextValue>(
    () => ({ session, signIn, signOut }),
    [session, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
