import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Select } from '../../components/Select';
import { Card, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as contentManagerApi from '../../api/contentManager';
import * as referenceApi from '../../api/reference';
import { formatDate } from '../../api/format';
import { fieldErrorsFor, messageFor } from '../../api/errors';
import { ChangePasswordCard } from '../../components/ChangePasswordCard';

/**
 * FR-CM-05 — the study field the content manager teaches, plus the account details around it.
 *
 * The field is not a preference: nothing can be uploaded until it is set, and it decides which
 * university-and-field combination every upload is filed under.
 */
export function StudyFieldPage() {
  const { session } = useAuth();
  const token = session!.token;

  const profile = useAsync(() => contentManagerApi.getProfile(token), [token]);
  const fields = useAsync(() => referenceApi.listStudyFields(token), [token]);
  const save = useAction(contentManagerApi.selectStudyField);

  const [draft, setDraft] = useState<number | undefined>(undefined);
  const [saved, setSaved] = useState(false);

  const current = profile.data?.studyFieldId;
  const selected = draft ?? current ?? '';
  const errors = fieldErrorsFor(save.error);

  const loading = profile.loading || fields.loading;
  const failed = profile.failed || fields.failed;

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    if (selected === '') return;
    const updated = await save.run(token, { studyFieldId: selected });
    if (updated) {
      // The PUT returns the whole updated account, so there is nothing to refetch.
      profile.setData(updated);
      setDraft(undefined);
      setSaved(true);
    }
  }

  const changing = current !== undefined && selected !== '' && selected !== current;

  return (
    <AppShell careerPath={profile.data?.studyFieldName}>
      <PageHeader
        title="My study field"
        lede="The field you teach in. Everything you upload is filed under it, and nothing can be uploaded until it is set."
      />

      {loading && <Skeleton rows={3} />}
      {!loading && failed && (
        <ErrorState
          message={messageFor(profile.error ?? fields.error)}
          onRetry={() => {
            profile.reload();
            fields.reload();
          }}
        />
      )}

      {!loading && !failed && profile.data && (
        <div className="stack">
          <Card>
            <h2 className="section__title">Your account</h2>
            <dl className="facts facts--flat">
              <div>
                <dt>Name</dt>
                <dd>
                  {profile.data.firstName} {profile.data.lastName}
                </dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd className="facts__plain">{profile.data.email}</dd>
              </div>
              <div>
                <dt>University</dt>
                <dd className="facts__plain">{profile.data.universityName ?? 'Not set'}</dd>
              </div>
              <div>
                <dt>Account created</dt>
                <dd className="facts__plain">{formatDate(profile.data.createdAt)}</dd>
              </div>
            </dl>
            {/* Only an administrator can change these — saying so is kinder than a form
                field that silently refuses, or no explanation at all. */}
            <p className="cell__quiet">
              Your name and university are set by an administrator and cannot be changed here.
            </p>
          </Card>

          <Card>
            <h2 className="section__title">Study field</h2>
            {save.failed && <Banner message={messageFor(save.error)} />}
            {saved && !save.failed && (
              <p className="notice notice--ok" role="status">
                Saved. You teach <strong>{profile.data.studyFieldName}</strong>.
              </p>
            )}

            {current === undefined && !saved && (
              <p className="notice notice--info">
                You have not chosen a field yet, so uploading is blocked. Pick one below to get
                started.
              </p>
            )}

            <form className="form" onSubmit={handleSave}>
              <Select
                label="The field you teach"
                placeholder="Choose a study field"
                value={selected}
                onChange={(e) => {
                  setDraft(Number(e.target.value));
                  setSaved(false);
                }}
                error={errors.studyFieldId}
                disabled={save.running}
                options={(fields.data ?? []).map((f) => ({
                  value: f.studyFieldId,
                  label: f.fieldName,
                }))}
              />

              {/* Changing it does not move existing uploads: each one keeps the
                  university-and-field it was filed under, so the list can legitimately show
                  more than one field afterwards. */}
              {changing && (
                <p className="notice notice--preview">
                  <strong>Changing your field affects new uploads only.</strong> Documents you
                  have already uploaded stay filed under{' '}
                  {profile.data.studyFieldName ?? 'their original field'}.
                </p>
              )}

              <div className="actions">
                <button
                  type="submit"
                  className="button button--primary button--auto"
                  disabled={save.running || selected === '' || selected === current}
                >
                  {save.running ? 'Saving…' : current === undefined ? 'Save field' : 'Change field'}
                </button>
                {current !== undefined && (
                  <Link className="button button--secondary button--auto" to="/content">
                    Go to learning outcomes
                  </Link>
                )}
              </div>
            </form>
          </Card>
        </div>
      )}

      <ChangePasswordCard />
    </AppShell>
  );
}
