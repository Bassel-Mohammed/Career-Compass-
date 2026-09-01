import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Session } from '../types';
import { AuthProvider } from './AuthProvider';
import { useAuth } from './useAuth';

const toastMocks = vi.hoisted(() => ({
  warning: vi.fn(),
  error: vi.fn(),
  dismiss: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: toastMocks }));
vi.mock('../api/auth', () => ({ logout: vi.fn() }));

function SessionStatus() {
  const { session } = useAuth();
  return <span>{session ? 'Signed in' : 'Signed out'}</span>;
}

describe('AuthProvider session expiry', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-28T12:00:00Z'));
    window.localStorage.clear();
    vi.clearAllMocks();

    const session: Session = {
      token: 'test-token',
      role: 'JOB_SEEKER',
      userId: 7,
      email: 'student@example.com',
      expiresAt: Date.now() + 30 * 60 * 1000,
    };
    window.localStorage.setItem('careercompass.session', JSON.stringify(session));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('warns at 29 minutes and signs the user out at 30 minutes', () => {
    render(
      <AuthProvider>
        <SessionStatus />
      </AuthProvider>,
    );

    expect(screen.getByText('Signed in')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(29 * 60 * 1000 - 1));
    expect(toastMocks.warning).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(toastMocks.warning).toHaveBeenCalledWith(
      'You will be signed out automatically in 1 minute. Save your work now.',
      expect.objectContaining({
        id: 'session-expiry-warning',
        duration: 60_000,
      }),
    );
    expect(screen.getByText('Signed in')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(60 * 1000));
    expect(screen.getByText('Signed out')).toBeInTheDocument();
    expect(window.localStorage.getItem('careercompass.session')).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith(
      'Your 30-minute session has ended. Please sign in again.',
      expect.objectContaining({ id: 'session-expired' }),
    );
  });
});
