import { AppShell } from '../../components/AppShell';
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  PrerequisiteState,
  PreviewBadge,
  ProgressBar,
  Skeleton,
} from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as jobMatchesApi from '../../api/jobMatches';
import { formatDate } from '../../api/format';
import { isNotInScope, messageFor, prerequisiteFor } from '../../api/errors';

/**
 * FR-JS-23.
 *
 * This capability is descoped from the AI contract for the current release. Against the real
 * service the backend answers 501 and says so; only the mock returns numbers, and its scores
 * are an explicit placeholder heuristic. Both states are surfaced honestly here rather than
 * dressed up as analysis — presenting a placeholder as a match score is the one thing this
 * screen must not do.
 */
export function JobsPage() {
  const { session } = useAuth();
  const matches = useAsync(() => jobMatchesApi.getJobMatches(session!.token), [session!.token]);

  const prereq = prerequisiteFor(matches.error, 'JOB_SEEKER');
  const descoped = isNotInScope(matches.error);
  const jobs = matches.data ?? [];
  const mocked = jobs.some((j) => jobMatchesApi.isMockText(j.explanation));

  return (
    <AppShell>
      <PageHeader
        title="Job matches"
        lede="Open roles ranked against the skills in your profile."
      />

      {matches.loading && <Skeleton rows={4} />}

      {!matches.loading && prereq && <PrerequisiteState to={prereq.to} message={prereq.message} />}

      {!matches.loading && descoped && (
        <EmptyState
          title="Job matching isn’t part of this release"
          body="The analysis service has no job-matching capability yet, so there is nothing to rank with. Everything else in your profile — skill gaps, courses, quizzes and mentors — works as normal."
        />
      )}

      {!matches.loading && matches.failed && !prereq && !descoped && (
        <ErrorState message={messageFor(matches.error)} onRetry={matches.reload} />
      )}

      {!matches.loading && !matches.failed && (
        <>
          {mocked && (
            <PreviewBadge>
              These scores come from a placeholder, not from real analysis — job matching is
              not part of the current release. Treat the ordering as a demonstration.
            </PreviewBadge>
          )}

          {jobs.length === 0 ? (
            <EmptyState
              title="No matching roles yet"
              body="No open postings scored against your profile. As employers post roles, matches appear here."
            />
          ) : (
            <ul className="stack list-reset">
              {jobs.map((job) => (
                <Card as="li" key={job.jobId} className="job">
                  <div className="job__head">
                    <div>
                      <h3 className="job__title">{job.jobTitle}</h3>
                      <p className="cell__quiet">{job.companyName}</p>
                    </div>
                    <span className="cell__quiet">{formatDate(job.matchedAt)}</span>
                  </div>
                  {/* Already 0..100 from the backend — but the mock can return long
                      decimals, so the bar rounds for display. */}
                  <ProgressBar value={job.matchScore} label={`${job.jobTitle} match`} />
                  {job.explanation && <p className="job__why">{job.explanation}</p>}
                </Card>
              ))}
            </ul>
          )}
        </>
      )}
    </AppShell>
  );
}
