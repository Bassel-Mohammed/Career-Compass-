import { useState } from 'react';
import { toast } from 'sonner';
import { Banner } from './Banner';
import { TextField } from './TextField';
import { Card } from './ui';
import { useAuth } from '../auth/useAuth';
import { useAction } from '../hooks/useAsync';
import * as authApi from '../api/auth';
import { fieldErrorsFor, messageFor } from '../api/errors';

/**
 * Password rotation, shared by every actor's profile screen.
 *
 * One component rather than five copies because the endpoint is role-agnostic — the token
 * says who is calling, so there is nothing per-actor to vary.
 *
 * On success the server revokes the current token, so the session this page is running in is
 * already dead. Signing the user out locally and sending them back to the sign-in screen is
 * therefore the honest ending: leaving them on a page whose every subsequent request would
 * 401 would look like the app breaking.
 */
export function ChangePasswordCard() {
  const { session, signOut } = useAuth();
  const change = useAction(authApi.changePassword);

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');

  const errors = fieldErrorsFor(change.error);

  // Checked here because the server never sees the confirmation field — it exists only to
  // catch a typo in something the user cannot read back.
  const mismatch = confirm.length > 0 && next !== confirm;
  const canSubmit =
    current.length > 0 && next.length >= 8 && next === confirm && !change.running;

  async function handleSubmit() {
    const done = await change.run(session!.token, {
      currentPassword: current,
      newPassword: next,
    });
    // useAction resolves to undefined on failure; void is a success here since the endpoint
    // returns 204, so the result cannot be truth-tested the way other calls are.
    if (change.failed || done === undefined) return;

    toast.success('Password changed. Sign in with your new password.');
    signOut();
  }

  return (
    <Card className="danger-zone">
      <h2 className="section__title">Change your password</h2>
      <p className="cell__quiet">
        You will be signed out afterwards, so the sessions opened with your old password cannot
        outlive it.
      </p>

      {change.failed && <Banner message={messageFor(change.error)} />}

      <div className="form">
        <TextField
          label="Current password"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          error={errors.currentPassword}
          disabled={change.running}
        />
        <TextField
          label="New password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          error={errors.newPassword}
          hint="At least 8 characters."
          disabled={change.running}
        />
        <TextField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={mismatch ? 'Passwords do not match.' : undefined}
          disabled={change.running}
        />
        <div className="actions">
          <button
            type="button"
            className="button button--primary button--auto"
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
          >
            {change.running ? 'Changing…' : 'Change password'}
          </button>
        </div>
      </div>
    </Card>
  );
}
