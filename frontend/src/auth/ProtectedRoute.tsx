import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from './useAuth';
import { homeFor } from './roles';
import type { Role } from '../types';

interface Props {
  /** Roles allowed through. A signed-in user of another role is sent to their own home. */
  allow: Role[];
  children: ReactNode;
}

export function ProtectedRoute({ allow, children }: Props) {
  const { session } = useAuth();
  const location = useLocation();

  if (!session) {
    // Remember where they were headed so sign-in can return them there.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (!allow.includes(session.role)) {
    return <Navigate to={homeFor(session.role)} replace />;
  }

  return <>{children}</>;
}
