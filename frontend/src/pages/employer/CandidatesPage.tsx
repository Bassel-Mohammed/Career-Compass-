import { Link, useParams } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  PreviewBadge,
  ProgressBar,
  Skeleton,
} from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as employerApi from '../../api/employer';
import { formatDate, formatPercent } from '../../api/format';
import { isNotInScope, messageFor } from '../../api/errors';

/** FR-EMP-11..13, with the current mock/501 boundary shown rather than hidden. */
export function CandidatesPage() {
  const { session } = useAuth();
  const params = useParams<{ jobId: string }>();
  const token = session!.token;
  const jobId = Number(params.jobId);
  const validJobId = Number.isInteger(jobId) && jobId > 0;

  const jobs = useAsync(() => employerApi.listJobs(token), [token]);
  const candidates = useAsync(
    () => (validJobId ? employerApi.listCandidates(token, jobId) : Promise.resolve([])),
    [token, validJobId, jobId],
  );
  const posting = validJobId ? jobs.data?.find((job) => job.jobId === jobId) : undefined;
  const missing = !jobs.loading && !jobs.failed && (!validJobId || posting === undefined);
  const descoped = isNotInScope(candidates.error);
  const rows = candidates.data ?? [];

  return (
    <AppShell>
      <PageHeader
        title={posting ? `Candidates for ${posting.title}` : 'Candidates'}
        lede="Review the skill evidence available for people matched to this posting."
        action={
          <Link className="button button--secondary button--auto" to="/employer">
            Back to postings
          </Link>
        }
      />

      {jobs.loading && <Skeleton rows={2} />}
      {!jobs.loading && jobs.failed && (
        <ErrorState message={messageFor(jobs.error)} onRetry={jobs.reload} />
      )}

      {missing && (
        <EmptyState
          title="Posting not found"
          body="This posting no longer exists, does not belong to your account, or its address is invalid."
          action={<Link className="button button--primary" to="/employer">Back to postings</Link>}
        />
      )}

      {!jobs.loading && !jobs.failed && !missing && candidates.loading && <Skeleton rows={4} />}

      {!jobs.loading && !jobs.failed && !missing && !candidates.loading && descoped && (
        <EmptyState
          title="Candidate ranking isn’t part of this release"
          body="The live analysis service returns 501 Not Implemented for job matching. Candidate scores only exist when the backend is deliberately running its development mock."
        />
      )}

      {!jobs.loading &&
        !jobs.failed &&
        !missing &&
        !candidates.loading &&
        candidates.failed &&
        !descoped && (
          <ErrorState message={messageFor(candidates.error)} onRetry={candidates.reload} />
        )}

      {!jobs.loading &&
        !jobs.failed &&
        !missing &&
        !candidates.loading &&
        !candidates.failed && (
          <div className="stack">
            <PreviewBadge>
              Candidate ranking is a development demonstration. These scores come from a
              placeholder heuristic, not real job-fit analysis, and must not be used as a
              hiring decision.
            </PreviewBadge>

            {rows.length === 0 ? (
              <EmptyState
                title="No candidates to demonstrate yet"
                body="Only students who have confirmed a transcript and built a skill profile can appear here."
              />
            ) : (
              <ul className="stack list-reset">
                {rows.map((candidate) => (
                  <Card as="li" key={candidate.jobseekerId} className="candidate">
                    <div className="candidate__head">
                      <div>
                        <h2 className="candidate__name">
                          {candidate.firstName} {candidate.lastName}
                        </h2>
                        <a className="candidate__email" href={`mailto:${candidate.email}`}>
                          {candidate.email}
                        </a>
                      </div>
                      <span className="cell__quiet">Calculated {formatDate(candidate.matchedAt)}</span>
                    </div>

                    <ProgressBar
                      value={candidate.matchScore}
                      label={`Placeholder match score for ${candidate.firstName} ${candidate.lastName}`}
                    />
                    {candidate.explanation && (
                      <p className="candidate__explanation">{candidate.explanation}</p>
                    )}

                    <section className="candidate__evidence">
                      <h3 className="candidate__subtitle">Skill profile used by the placeholder</h3>
                      {candidate.skillInsights.length === 0 ? (
                        <p className="cell__quiet">No individual skill scores were returned.</p>
                      ) : (
                        <ul className="candidate__skills list-reset">
                          {candidate.skillInsights.map((skill, index) => (
                            <li key={`${skill.skillName}-${index}`}>
                              <span>{skill.skillName}</span>
                              <strong>{formatPercent(skill.score)}</strong>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>

                    <div className="posting__actions">
                      <a
                        className="button button--secondary button--small button--auto"
                        href={`mailto:${candidate.email}`}
                      >
                        Email candidate
                      </a>
                    </div>
                  </Card>
                ))}
              </ul>
            )}
          </div>
        )}
    </AppShell>
  );
}
