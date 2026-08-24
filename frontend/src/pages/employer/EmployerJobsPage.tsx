import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as employerApi from '../../api/employer';
import { formatDate } from '../../api/format';
import { messageFor } from '../../api/errors';
import type { JobResponse } from '../../types';

/** Give a successful void DELETE a value so useAction can distinguish it from a failure. */
async function removeJob(token: string, jobId: number): Promise<number> {
  await employerApi.deleteJob(token, jobId);
  return jobId;
}

/** FR-EMP-07..10 — the employer's posting inventory and its destructive action. */
export function EmployerJobsPage() {
  const { session } = useAuth();
  const token = session!.token;
  const jobs = useAsync(() => employerApi.listJobs(token), [token]);
  const remove = useAction(removeJob);
  const [removing, setRemoving] = useState<JobResponse | null>(null);

  const rows = [...(jobs.data ?? [])].sort((a, b) => b.postedAt.localeCompare(a.postedAt));

  async function handleDelete() {
    if (!removing) return;
    const deletedId = await remove.run(token, removing.jobId);
    setRemoving(null);
    if (deletedId !== undefined) {
      jobs.setData((jobs.data ?? []).filter((job) => job.jobId !== deletedId));
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Job postings"
        lede="Create roles, keep their requirements current, and review candidates for each posting."
        action={
          <Link className="button button--primary button--auto" to="/employer/jobs/new">
            Create posting
          </Link>
        }
      />

      {jobs.loading && <Skeleton rows={4} />}
      {!jobs.loading && jobs.failed && (
        <ErrorState message={messageFor(jobs.error)} onRetry={jobs.reload} />
      )}

      {!jobs.loading && !jobs.failed && rows.length === 0 && (
        <EmptyState
          title="No job postings yet"
          body="Create your first posting with a role description and the skills candidates should bring."
          action={
            <Link className="button button--primary" to="/employer/jobs/new">
              Create the first posting
            </Link>
          }
        />
      )}

      {!jobs.loading && !jobs.failed && rows.length > 0 && (
        <div className="stack">
          {remove.failed && <Banner message={messageFor(remove.error)} />}
          <ul className="stack list-reset">
            {rows.map((job) => (
              <Card as="li" key={job.jobId} className="posting">
                <div className="posting__head">
                  <div>
                    <h2 className="posting__title">{job.title}</h2>
                    <p className="cell__quiet">Posted {formatDate(job.postedAt)}</p>
                  </div>
                  <span className={`badge badge--${job.isActive ? 'strong' : 'unknown'}`}>
                    {job.isActive ? 'Active' : 'Inactive'}
                  </span>
                </div>

                <p className="posting__description">{job.description || 'No description provided.'}</p>

                <div className="posting__meta">
                  <span>{job.studyFieldName ?? 'Any study field'}</span>
                  <span>{job.requiredSkills?.trim() || 'No required skills listed'}</span>
                </div>

                <div className="posting__actions">
                  <Link
                    className="button button--primary button--small button--auto"
                    to={`/employer/jobs/${job.jobId}/candidates`}
                  >
                    Review candidates
                  </Link>
                  <Link
                    className="button button--secondary button--small button--auto"
                    to={`/employer/jobs/${job.jobId}/edit`}
                  >
                    Edit
                  </Link>
                  <button
                    type="button"
                    className="button button--quiet button--small button--auto"
                    onClick={() => {
                      remove.clearError();
                      setRemoving(job);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </Card>
            ))}
          </ul>
        </div>
      )}

      {removing && (
        <ConfirmDialog
          title="Delete this job posting?"
          body={`“${removing.title}” and its stored job matches will be permanently deleted. This cannot be undone.`}
          confirmLabel="Delete posting"
          destructive
          busy={remove.running}
          onConfirm={() => void handleDelete()}
          onCancel={() => setRemoving(null)}
        />
      )}
    </AppShell>
  );
}
