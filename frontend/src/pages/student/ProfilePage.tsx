import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { TextField } from '../../components/TextField';
import { Card, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as jobSeekerApi from '../../api/jobSeeker';
import { formatDate } from '../../api/format';
import { fieldErrorsFor, messageFor } from '../../api/errors';
import { ChangePasswordCard } from '../../components/ChangePasswordCard';

import { toast } from 'sonner';

/** FR-JS-06/07/08, plus the disclosures nothing in the backend makes on its own. */
export function ProfilePage() {
  const { session, signOut } = useAuth();
  const navigate = useNavigate();
  const token = session!.token;

  const profile = useAsync(() => jobSeekerApi.getProfile(token), [token]);
  const save = useAction(jobSeekerApi.updateProfile);
  const remove = useAction(jobSeekerApi.deleteProfile);

  const [draft, setDraft] = useState<{ firstName?: string; lastName?: string }>({});
  const [confirming, setConfirming] = useState(false);

  const firstName = draft.firstName ?? profile.data?.firstName ?? '';
  const lastName = draft.lastName ?? profile.data?.lastName ?? '';
  const errors = fieldErrorsFor(save.error);

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    const saved = await save.run(token, { firstName, lastName });
    if (saved) {
      setDraft({});
      profile.setData(saved);
      toast.success('Profile updated successfully');
    } else {
      toast.error('Failed to update profile');
    }
  }

  async function handleDelete() {
    const done = await remove.run(token);
    if (done !== undefined) {
      // The account is gone, so the token is worthless — drop the session and start over.
      toast.success('Account deleted permanently');
      await signOut();
      navigate('/login', { replace: true });
    } else {
      toast.error('Failed to delete account');
      setConfirming(false);
    }
  }

  return (
    <AppShell careerPath={profile.data?.careerPathTitle}>
      <PageHeader title="Profile" lede="Your account, and what the system does with your data." />

      {profile.loading && <Skeleton rows={3} />}
      {!profile.loading && profile.failed && (
        <ErrorState message={messageFor(profile.error)} onRetry={profile.reload} />
      )}

      {!profile.loading && profile.data && (
        <div className="stack">
          <Card>
            <h2 className="section__title">Your details</h2>
            {save.failed && <Banner message={messageFor(save.error)} />}
            <form className="form" onSubmit={handleSave}>
              <div className="form__row">
                <TextField
                  label="First name"
                  value={firstName}
                  onChange={(e) => setDraft((d) => ({ ...d, firstName: e.target.value }))}
                  error={errors.firstName}
                  disabled={save.running}
                  maxLength={100}
                />
                <TextField
                  label="Last name"
                  value={lastName}
                  onChange={(e) => setDraft((d) => ({ ...d, lastName: e.target.value }))}
                  error={errors.lastName}
                  disabled={save.running}
                  maxLength={100}
                />
              </div>
              <TextField label="Email" value={profile.data.email} disabled readOnly
                hint="Your email cannot be changed here." />
              <div className="actions">
                <button
                  type="submit"
                  className="button button--primary button--auto"
                  disabled={save.running}
                >
                  {save.running ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </form>
          </Card>

          <Card>
            <h2 className="section__title">Your studies</h2>
            <dl className="facts facts--flat">
              <div>
                <dt>University</dt>
                <dd>{profile.data.universityName ?? 'Not set'}</dd>
              </div>
              <div>
                <dt>Study field</dt>
                <dd>{profile.data.studyFieldName ?? 'Not set'}</dd>
              </div>
              <div>
                <dt>Career path</dt>
                <dd>{profile.data.careerPathTitle ?? 'Not set'}</dd>
              </div>
              <div>
                <dt>Joined</dt>
                <dd>{formatDate(profile.data.createdAt)}</dd>
              </div>
            </dl>
            <p className="cell__quiet">
              Changing your career path re-measures every skill against the new one.{' '}
              <Link to="/setup">Change these</Link>.
            </p>
          </Card>

          {/* NFR-PRIV-04 and NFR-LEG-03 are UI-only obligations — nothing in the backend
              discloses either, so if this screen does not say it, nobody does. */}
          <Card>
            <h2 className="section__title">How your data is used</h2>
            <p className="cell__quiet">
              Your transcript is processed by an AI service to identify the skills behind your
              courses. The results are an advisory estimate, not a guarantee — scores,
              recommendations and matches are generated automatically and can be wrong. Your
              raw transcript file is not kept once the courses have been extracted from it.
            </p>
          </Card>

          <Card className="danger-zone">
            <h2 className="section__title">Delete your account</h2>
            <p className="cell__quiet">
              This removes your profile, your academic records, your skill profile, your
              quizzes and your matches. It cannot be undone.
            </p>
            {remove.failed && <Banner message={messageFor(remove.error)} />}
            <div className="actions">
              <button
                type="button"
                className="button button--danger button--auto"
                onClick={() => setConfirming(true)}
              >
                Delete my account
              </button>
            </div>
          </Card>
        </div>
      )}

      {confirming && (
        <ConfirmDialog
          title="Delete your account?"
          body="Everything the system holds about you is removed permanently — your transcript data, skill profile, quiz results and bookings. This cannot be undone."
          confirmLabel="Delete everything"
          destructive
          busy={remove.running}
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirming(false)}
        />
      )}

      <ChangePasswordCard />
    </AppShell>
  );
}
