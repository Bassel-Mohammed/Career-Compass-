import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Select } from '../../components/Select';
import { Banner } from '../../components/Banner';
import { Card, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as referenceApi from '../../api/reference';
import * as jobSeekerApi from '../../api/jobSeeker';
import { fieldErrorsFor, messageFor } from '../../api/errors';
import type { CareerPathResponse } from '../../types';

/**
 * FR-JS-07 and FR-JS-09 on one screen, because they are one decision in the student's mind
 * and because the second depends on the first: the career paths on offer are the ones open
 * to the chosen study field.
 *
 * Everything downstream is gated on these two values — confirming a transcript, the skill
 * dashboard, course recommendations, job matches and the mentor list all refuse to run
 * without them — so this is the first screen a new student sees.
 */
export function SetupPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const token = session!.token;

  const profile = useAsync(() => jobSeekerApi.getProfile(token), [token]);
  const fields = useAsync(() => referenceApi.listStudyFields(token), [token]);
  const paths = useAsync(() => referenceApi.listCareerPaths(token), [token]);
  const universities = useAsync(() => referenceApi.listUniversities(token), [token]);

  /**
   * Only what the student has actually changed. Everything else falls through to the saved
   * profile, so the form is populated the moment it loads without an effect copying values
   * into state — and without a race where a slow profile response overwrites a fast typist.
   */
  const [draft, setDraft] = useState<{
    universityId?: number;
    studyFieldId?: number;
    careerPathId?: number;
  }>({});

  const universityId = draft.universityId ?? profile.data?.universityId ?? '';
  const studyFieldId = draft.studyFieldId ?? profile.data?.studyFieldId ?? '';
  const chosenPathId = draft.careerPathId ?? profile.data?.careerPathId ?? '';

  const save = useAction(jobSeekerApi.updateProfile);

  const loading = profile.loading || fields.loading || paths.loading || universities.loading;
  const loadFailed = profile.failed || fields.failed || paths.failed || universities.failed;
  const loadError = profile.error ?? fields.error ?? paths.error ?? universities.error;

  const available: CareerPathResponse[] = referenceApi.pathsForStudyField(
    paths.data ?? [],
    studyFieldId === '' ? undefined : studyFieldId,
  );

  // Changing study field can strand a path that is no longer on offer. Treated as unset by
  // derivation rather than cleared in an effect, so the form can never submit a combination
  // the student cannot see on screen.
  const careerPathId = available.some((p) => p.careerPathId === chosenPathId) ? chosenPathId : '';

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const saved = await save.run(token, {
      universityId: universityId === '' ? undefined : universityId,
      studyFieldId: studyFieldId === '' ? undefined : studyFieldId,
      careerPathId: careerPathId === '' ? undefined : careerPathId,
    });
    if (saved) navigate('/transcript');
  }

  const errors = fieldErrorsFor(save.error);
  const ready = studyFieldId !== '' && careerPathId !== '';

  return (
    <AppShell careerPath={profile.data?.careerPathTitle}>
      <PageHeader
        title="Set up your profile"
        lede="Your study field decides which career paths are open to you, and the career path is what every skill score is measured against. You can change both later."
      />

      {loading && <Skeleton rows={4} />}
      {!loading && loadFailed && (
        <ErrorState
          message={messageFor(loadError)}
          onRetry={() => {
            profile.reload();
            fields.reload();
            paths.reload();
            universities.reload();
          }}
        />
      )}

      {!loading && !loadFailed && (
        <form className="stack" onSubmit={handleSubmit}>
          {save.failed && <Banner message={messageFor(save.error)} />}

          <Card>
            <div className="form">
              <Select
                label="University"
                optional
                placeholder="Select your university"
                value={universityId}
                onChange={(e) => setDraft((d) => ({ ...d, universityId: Number(e.target.value) }))}
                error={errors.universityId}
                disabled={save.running}
                options={(universities.data ?? []).map((u) => ({
                  value: u.universityId,
                  label: u.universityName,
                }))}
              />

              <Select
                label="Study field"
                placeholder="Select what you study"
                value={studyFieldId}
                onChange={(e) => setDraft((d) => ({ ...d, studyFieldId: Number(e.target.value) }))}
                error={errors.studyFieldId}
                hint="Mentors are matched within your own field."
                disabled={save.running}
                options={(fields.data ?? []).map((f) => ({
                  value: f.studyFieldId,
                  label: f.fieldName,
                }))}
              />
            </div>
          </Card>

          <section>
            <h2 className="section__title">Career path</h2>
            <p className="section__lede">
              {studyFieldId === ''
                ? 'Pick a study field above to narrow these down.'
                : `${available.length} path${available.length === 1 ? '' : 's'} open to your field.`}
            </p>

            <ul className="grid list-reset">
              {available.map((path) => {
                const selected = path.careerPathId === careerPathId;
                return (
                  <li key={path.careerPathId}>
                    <label className={`choice${selected ? ' choice--on' : ''}`}>
                      <input
                        type="radio"
                        name="careerPath"
                        className="visually-hidden"
                        checked={selected}
                        disabled={save.running}
                        onChange={() => setDraft((d) => ({ ...d, careerPathId: path.careerPathId }))}
                      />
                      <span className="choice__title">{path.title}</span>
                      {path.description && (
                        <span className="choice__body">{path.description}</span>
                      )}
                    </label>
                  </li>
                );
              })}
            </ul>
            {errors.careerPathId && (
              <p className="field__error" role="alert">
                {errors.careerPathId}
              </p>
            )}
          </section>

          <div className="actions">
            <button
              type="submit"
              className="button button--primary button--auto"
              disabled={save.running || !ready}
            >
              {save.running ? 'Saving…' : 'Save and continue'}
            </button>
            {!ready && (
              <span className="actions__hint">
                Choose a study field and a career path to continue.
              </span>
            )}
          </div>
        </form>
      )}
    </AppShell>
  );
}
