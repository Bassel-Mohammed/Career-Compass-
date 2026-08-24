import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Select } from '../../components/Select';
import { TextArea } from '../../components/TextArea';
import { TextField } from '../../components/TextField';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as employerApi from '../../api/employer';
import * as referenceApi from '../../api/reference';
import { fieldErrorsFor, messageFor } from '../../api/errors';
import type { JobPostRequest, JobResponse } from '../../types';

interface JobDraft {
  title?: string;
  description?: string;
  requiredSkills?: string;
  studyFieldId?: number | '';
}

async function saveJob(
  token: string,
  jobId: number | null,
  body: JobPostRequest,
): Promise<JobResponse> {
  return jobId === null
    ? employerApi.createJob(token, body)
    : employerApi.updateJob(token, jobId, body);
}

/** FR-EMP-07..09 — one form for create and the backend's full-replace edit. */
export function JobFormPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const params = useParams<{ jobId: string }>();
  const token = session!.token;

  const editing = params.jobId !== undefined;
  const parsedJobId = Number(params.jobId);
  const validJobId = editing && Number.isInteger(parsedJobId) && parsedJobId > 0;

  const fields = useAsync(() => referenceApi.listStudyFields(token), [token]);
  const jobs = useAsync(
    () => (validJobId ? employerApi.listJobs(token) : Promise.resolve([])),
    [token, validJobId, parsedJobId],
  );
  const save = useAction(saveJob);
  const [draft, setDraft] = useState<JobDraft>({});
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  const existing = validJobId ? jobs.data?.find((job) => job.jobId === parsedJobId) : undefined;
  const title = draft.title ?? existing?.title ?? '';
  const description = draft.description ?? existing?.description ?? '';
  const requiredSkills = draft.requiredSkills ?? existing?.requiredSkills ?? '';
  const studyFieldId = draft.studyFieldId ?? existing?.studyFieldId ?? '';
  const errors = { ...fieldErrorsFor(save.error), ...clientErrors };

  const loading = fields.loading || (validJobId && jobs.loading);
  const failed = fields.failed || (validJobId && jobs.failed);
  const missing = validJobId && !jobs.loading && !jobs.failed && existing === undefined;

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!title.trim()) next.title = 'A job title is required';
    else if (title.trim().length > 200) next.title = 'Job title must be 200 characters or fewer';
    if (!description.trim()) next.description = 'A job description is required';
    setClientErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!validate()) return;

    const saved = await save.run(token, editing ? parsedJobId : null, {
      title: title.trim(),
      description: description.trim(),
      requiredSkills: requiredSkills.trim() || undefined,
      studyFieldId: studyFieldId === '' ? undefined : studyFieldId,
    });
    if (saved) navigate('/employer', { replace: true });
  }

  if (editing && !validJobId) {
    return (
      <AppShell>
        <PageHeader title="Edit job posting" />
        <EmptyState
          title="Posting not found"
          body="This job-posting address is not valid. Return to your postings and choose one there."
          action={<Link className="button button--primary" to="/employer">Back to postings</Link>}
        />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title={editing ? 'Edit job posting' : 'Create job posting'}
        lede={
          editing
            ? 'Update the complete posting. Saving replaces its current title, description, skills and study field.'
            : 'Describe the role and the skills a strong candidate should bring.'
        }
      />

      {loading && <Skeleton rows={5} />}
      {!loading && failed && (
        <ErrorState
          message={messageFor(fields.error ?? jobs.error)}
          onRetry={() => {
            fields.reload();
            if (validJobId) jobs.reload();
          }}
        />
      )}

      {!loading && !failed && missing && (
        <EmptyState
          title="Posting not found"
          body="This posting no longer exists, or it does not belong to your account."
          action={<Link className="button button--primary" to="/employer">Back to postings</Link>}
        />
      )}

      {!loading && !failed && !missing && (
        <Card>
          {save.failed && <Banner message={messageFor(save.error)} />}
          <form className="form" onSubmit={handleSubmit}>
            <TextField
              label="Job title"
              value={title}
              onChange={(event) => {
                setDraft((current) => ({ ...current, title: event.target.value }));
                setClientErrors((current) => ({ ...current, title: '' }));
              }}
              error={errors.title || undefined}
              placeholder="Backend Engineer"
              maxLength={200}
              required
              autoFocus
              disabled={save.running}
            />

            <TextArea
              label="Job description"
              value={description}
              onChange={(event) => {
                setDraft((current) => ({ ...current, description: event.target.value }));
                setClientErrors((current) => ({ ...current, description: '' }));
              }}
              error={errors.description || undefined}
              placeholder="Responsibilities, experience and what success in the role looks like."
              rows={8}
              required
              disabled={save.running}
            />

            <TextArea
              label="Required skills"
              optional
              value={requiredSkills}
              onChange={(event) =>
                setDraft((current) => ({ ...current, requiredSkills: event.target.value }))
              }
              error={errors.requiredSkills}
              hint="Free text for now. Separate skills with commas to keep the posting readable."
              placeholder="Java, Spring Boot, SQL, REST APIs"
              rows={3}
              disabled={save.running}
            />

            <Select
              label="Study field"
              optional
              value={studyFieldId}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  studyFieldId: event.target.value === '' ? '' : Number(event.target.value),
                }))
              }
              error={errors.studyFieldId}
              hint="Choose a field when the role specifically targets graduates from it."
              options={[
                { value: '', label: 'Any study field' },
                ...(fields.data ?? []).map((field) => ({
                  value: field.studyFieldId,
                  label: field.fieldName,
                })),
              ]}
              disabled={save.running}
            />

            <div className="actions">
              <button
                type="submit"
                className="button button--primary button--auto"
                disabled={save.running}
              >
                {save.running ? 'Saving…' : editing ? 'Save changes' : 'Publish posting'}
              </button>
              <Link className="button button--secondary button--auto" to="/employer">
                Cancel
              </Link>
            </div>
          </form>
        </Card>
      )}
    </AppShell>
  );
}
