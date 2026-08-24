import { Link } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import {
  Card,
  ErrorState,
  PageHeader,
  PrerequisiteState,
  ProgressBar,
  Skeleton,
  Stat,
  StatusBadge,
} from '../../components/ui';
import { normalise } from '../../components/status';
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as transcriptApi from '../../api/transcript';
import { formatPercent } from '../../api/format';
import { messageFor, prerequisiteFor } from '../../api/errors';

/**
 * FR-JS-14 and FR-JS-21 — the home screen once a student is set up.
 *
 * Recomputed by the backend on every visit rather than read from a cache, so it always
 * reflects the latest grades, career path and quiz results, and always costs an AI round
 * trip. Hence the skeleton rather than an empty flash (NFR-USE-04).
 */
export function DashboardPage() {
  const { session } = useAuth();
  const dashboard = useAsync(() => transcriptApi.getSkillDashboard(session!.token), [
    session!.token,
  ]);

  const prereq = prerequisiteFor(dashboard.error, 'JOB_SEEKER');
  const data = dashboard.data;

  const strong = data?.skills.filter((s) => normalise(s.classification) === 'Strong').length ?? 0;
  const weak = data?.skills.filter((s) => normalise(s.classification) === 'Weak').length ?? 0;

  return (
    <AppShell careerPath={data?.careerPathTitle}>
      <PageHeader
        title="Skill dashboard"
        lede={
          data
            ? `What your coursework says you can do, measured against ${data.careerPathTitle}.`
            : 'What your coursework says you can do, measured against your career path.'
        }
        action={
          data && (
            <Link className="button button--secondary button--auto" to="/courses">
              See course recommendations
            </Link>
          )
        }
      />

      {dashboard.loading && <Skeleton rows={5} />}

      {!dashboard.loading && prereq && (
        <PrerequisiteState to={prereq.to} message={prereq.message} />
      )}

      {!dashboard.loading && dashboard.failed && !prereq && (
        <ErrorState message={messageFor(dashboard.error)} onRetry={dashboard.reload} />
      )}

      {!dashboard.loading && data && (
        <>
          <div className="grid grid--stats">
            <Stat
              label="Overall readiness"
              value={formatPercent(data.overallReadinessPercent)}
              hint={`for ${data.careerPathTitle}`}
            />
            <Stat label="Strong skills" value={strong} hint="at or above target" />
            <Stat label="Weak skills" value={weak} hint="the gap to close" />
          </div>

          {/* FR-JS-22: say plainly where the numbers came from. A dashboard built from
              grades alone is a weaker claim than one backed by quiz evidence, and the
              student cannot tell the difference by looking at it. */}
          <p className="notice notice--info">
            {data.basedOnQuizResults ? (
              <>
                <strong>Refined by your quiz results.</strong> Skills you have been quizzed on
                use that evidence instead of your grades.
              </>
            ) : (
              <>
                <strong>Estimated from your grades.</strong> You have not completed any quizzes
                yet — <Link to="/quizzes">take one</Link> to replace an estimate with evidence.
              </>
            )}
          </p>

          {data.skills.length === 0 ? (
            <Card>
              <p className="cell__quiet">
                No skills could be derived from your courses yet. This usually means the
                courses on your transcript have no extracted syllabus behind them.
              </p>
            </Card>
          ) : (
            <Card>
              <h2 className="section__title">
                Skills, weakest first
                <span className="section__count">{data.skills.length}</span>
              </h2>
              {/* The service sorts weakest-first deliberately so the gaps read first.
                  Do not re-sort. */}
              <ul className="list-reset skills">
                {data.skills.map((skill) => (
                  <li key={skill.canonicalSkillId ?? skill.skillName} className="skills__row">
                    <div className="skills__head">
                      <span className="skills__name">{skill.skillName ?? 'Unnamed skill'}</span>
                      <StatusBadge status={skill.classification} />
                    </div>
                    <ProgressBar
                      value={skill.score}
                      status={skill.classification}
                      label={`${skill.skillName ?? 'Skill'} score`}
                    />
                    {/* Null against the real AI service — per-skill prose is not in the
                        v1 contract — so this renders only when something is there. */}
                    {skill.explanation && <p className="skills__why">{skill.explanation}</p>}
                    {skill.canonicalSkillId && normalise(skill.classification) !== 'Strong' && (
                      <Link
                        className="skills__action"
                        to={`/quizzes?skill=${encodeURIComponent(skill.canonicalSkillId)}&name=${encodeURIComponent(skill.skillName ?? '')}`}
                      >
                        Take a quiz to refine this
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </AppShell>
  );
}
