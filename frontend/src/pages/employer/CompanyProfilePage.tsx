import { useState } from 'react';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { TextArea } from '../../components/TextArea';
import { TextField } from '../../components/TextField';
import { Card, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as employerApi from '../../api/employer';
import { fieldErrorsFor, messageFor } from '../../api/errors';
import { ChangePasswordCard } from '../../components/ChangePasswordCard';
import { formatDate } from '../../api/format';

interface ProfileDraft {
  companyName?: string;
  industry?: string;
  companyDescription?: string;
}

import { toast } from 'sonner';

/** FR-EMP-05/06 — registration creates the profile; this screen maintains it. */
export function CompanyProfilePage() {
  const { session } = useAuth();
  const token = session!.token;
  const profile = useAsync(() => employerApi.getProfile(token), [token]);
  const save = useAction(employerApi.updateProfile);
  const [draft, setDraft] = useState<ProfileDraft>({});
  const [nameError, setNameError] = useState<string | undefined>();

  const companyName = draft.companyName ?? profile.data?.companyName ?? '';
  const industry = draft.industry ?? profile.data?.industry ?? '';
  const companyDescription = draft.companyDescription ?? profile.data?.companyDescription ?? '';
  const errors = fieldErrorsFor(save.error);

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    const trimmedName = companyName.trim();
    if (!trimmedName) {
      setNameError('A company name is required');
      return;
    }

    const updated = await save.run(token, {
      companyName: trimmedName,
      industry: industry.trim(),
      companyDescription: companyDescription.trim(),
    });
    if (updated) {
      profile.setData(updated);
      setDraft({});
      toast.success('Company profile saved');
    } else {
      toast.error('Failed to save company profile');
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Company profile"
        lede="The organisation details shown alongside every job you publish."
      />

      {profile.loading && <Skeleton rows={4} />}
      {!profile.loading && profile.failed && (
        <ErrorState message={messageFor(profile.error)} onRetry={profile.reload} />
      )}

      {!profile.loading && profile.data && (
        <div className="stack">
          <Card>
            <h2 className="section__title">Company details</h2>
            <p className="section__lede">
              Keep this current so candidates can understand who is hiring them.
            </p>

            {save.failed && <Banner message={messageFor(save.error)} />}

            <form className="form" onSubmit={handleSave}>
              <TextField
                label="Company name"
                value={companyName}
                onChange={(event) => {
                  setDraft((current) => ({ ...current, companyName: event.target.value }));
                  setNameError(undefined);
                }}
                error={nameError ?? errors.companyName}
                maxLength={200}
                required
                disabled={save.running}
              />

              <TextField
                label="Industry"
                optional
                value={industry}
                onChange={(event) => {
                  setDraft((current) => ({ ...current, industry: event.target.value }));
                }}
                error={errors.industry}
                placeholder="Software and technology"
                maxLength={150}
                disabled={save.running}
              />

              <TextArea
                label="Company description"
                optional
                value={companyDescription}
                onChange={(event) => {
                  setDraft((current) => ({ ...current, companyDescription: event.target.value }));
                }}
                error={errors.companyDescription}
                placeholder="What your company does, its mission and what candidates can expect."
                maxLength={2000}
                rows={7}
                disabled={save.running}
              />

              <TextField
                label="Account email"
                value={profile.data.email}
                hint="Your sign-in email cannot be changed here."
                readOnly
                disabled
              />

              <div className="actions">
                <button
                  type="submit"
                  className="button button--primary button--auto"
                  disabled={save.running}
                >
                  {save.running ? 'Saving…' : 'Save profile'}
                </button>
                <span className="actions__hint">
                  Company account created {formatDate(profile.data.createdAt)}.
                </span>
              </div>
            </form>
          </Card>
        </div>
      )}

      <ChangePasswordCard />
    </AppShell>
  );
}
