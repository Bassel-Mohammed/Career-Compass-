import { createContext } from 'react';
import type { AuthResponse, Session } from '../types';

export interface AuthContextValue {
  session: Session | null;
  /** Store the result of a successful login or registration. */
  signIn: (auth: AuthResponse) => Session;
  /** Revoke the token server-side, then forget it locally. */
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
