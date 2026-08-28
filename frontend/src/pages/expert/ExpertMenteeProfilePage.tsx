import { useParams, Link } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Card, ErrorState, PageHeader, Skeleton, Stat, EmptyState } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as expertApi from '../../api/expert';
import { messageFor } from '../../api/errors';

export function ExpertMenteeProfilePage() {
  const { session } = useAuth();
  const { jobseekerId } = useParams<{ jobseekerId: string }>();
  const id = parseInt(jobseekerId || '0', 10);

  const dashboard = useAsync(() => expertApi.getJobSeekerDashboard(session!.token, id), [session!.token, id]);
  const recommendations = useAsync(() => expertApi.getJobSeekerRecommendations(session!.token, id), [session!.token, id]);

  const dashData = dashboard.data;
  const recData = recommendations.data;

  return (
    <AppShell>
      <PageHeader
        title={'Mentee Profile'}
        lede={dashData ? `Career path: ${dashData.careerPathTitle}` : 'Skill profile and recommendations'}
        action={
          <Link className="button button--secondary button--auto" to="/expert">
            Back to Sessions
          </Link>
        }
      />

      {(dashboard.loading || recommendations.loading) && <Skeleton rows={6} />}

      {(dashboard.failed || recommendations.failed) && (
        <ErrorState
          message={messageFor(dashboard.error || recommendations.error)}
          onRetry={() => { dashboard.reload(); recommendations.reload(); }}
        />
      )}

      {!dashboard.loading && !recommendations.loading && dashData && (
        <div className="stack stack--large">
          <section className="dashboard-stats">
            <Stat label="Total Analyzed Skills" value={dashData.skills.length} />
            <Stat label="Overall Readiness" value={`${dashData.overallReadinessPercent}%`} />
          </section>

          <Card as="section">
            <h2 className="section__title">Identified Skill Gaps</h2>
            {dashData.skills.filter(s => s.score < 50).length === 0 ? (
              <EmptyState title="No major gaps" body="The student meets all core requirements." />
            ) : (
              <ul className="stack list-reset">
                {dashData.skills.filter(s => s.score < 50).map((skill) => (
                  <li key={skill.canonicalSkillId} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
                    <strong>{skill.skillName}</strong>
                    <span className="cell__quiet">Score: {skill.score}%</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {recData && (
            <Card as="section">
              <h2 className="section__title">Recommended Courses</h2>
              {recData.length === 0 ? (
                <EmptyState title="No recommendations" body="No courses match the identified gaps." />
              ) : (
                <ul className="stack list-reset">
                  {recData.map((course) => (
                    <li key={course.recommendationId} style={{ borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
                      <h3 style={{ margin: '0 0 0.25rem 0' }}>{course.courseName}</h3>
                      {course.targetedSkillName && <p className="cell__quiet" style={{ margin: 0 }}>Targets: {course.targetedSkillName}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
      )}
    </AppShell>
  );
}
