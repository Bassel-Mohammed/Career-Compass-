import { AppShell } from '../../components/AppShell';
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
} from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as jobSeekerApi from '../../api/jobSeeker';
import { formatDate } from '../../api/format';
import { messageFor } from '../../api/errors';

export function JobsPage() {
  const { session } = useAuth();

  // Use listActiveJobs as a fallback since AI matching is descoped.
  const jobsReq = useAsync(() => jobSeekerApi.listActiveJobs(session!.token), [session!.token]);

  const jobs = jobsReq.data?.content ?? [];

  return (
    <AppShell>
      <PageHeader
        title="Open Roles"
        lede="Active opportunities posted by employers."
      />

      {jobsReq.loading && <Skeleton rows={4} />}

      {!jobsReq.loading && jobsReq.failed && (
        <ErrorState message={messageFor(jobsReq.error)} onRetry={jobsReq.reload} />
      )}

      {!jobsReq.loading && !jobsReq.failed && (
        <>
          {jobs.length === 0 ? (
            <EmptyState
              title="No open roles yet"
              body="No open postings have been created by employers. Please check back later."
            />
          ) : (
            <ul className="stack list-reset">
              {jobs.map((job) => (
                <Card as="li" key={job.jobId} className="job">
                  <div className="job__head">
                    <div>
                      <h3 className="job__title">{job.title}</h3>
                      <p className="cell__quiet">{job.companyName}</p>
                    </div>
                    {job.postedAt && <span className="cell__quiet">{formatDate(job.postedAt)}</span>}
                  </div>
                  {job.description && <p className="job__why">{job.description}</p>}
                </Card>
              ))}
            </ul>
          )}
        </>
      )}
    </AppShell>
  );
}
