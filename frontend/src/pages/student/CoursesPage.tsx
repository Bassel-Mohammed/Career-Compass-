import { useMemo } from 'react';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  PrerequisiteState,
  Skeleton,
} from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as recommendationsApi from '../../api/recommendations';
import { formatDate } from '../../api/format';
import { messageFor, prerequisiteFor } from '../../api/errors';
import type { CourseRecommendationItem } from '../../types';

const UNGROUPED = '__ungrouped__';

/**
 * FR-JS-15/16.
 *
 * Two endpoints back this one screen and they return different things. `generate` recomputes
 * from the student's current weak skills and is the only call that says which skill each
 * course targets and why; the stored rows have no columns for either, so reading them back
 * later loses that. The screen therefore shows grouped, explained results right after
 * generating and a plainer list afterwards — and says so, rather than letting the explanation
 * silently vanish on the next visit.
 */
export function CoursesPage() {
  const { session } = useAuth();
  const token = session!.token;

  const stored = useAsync(() => recommendationsApi.listRecommendations(token), [token]);
  const generate = useAction(recommendationsApi.generateRecommendations);

  // A fresh generate overwrites the loaded list in place (see handleGenerate), so this
  // one array is both the stored rows and the richer just-generated ones.
  const items: CourseRecommendationItem[] = stored.data ?? [];

  const grouped = useMemo(() => {
    const groups = new Map<string, CourseRecommendationItem[]>();
    for (const item of stored.data ?? []) {
      const key = item.targetedSkillName ?? UNGROUPED;
      const list = groups.get(key);
      if (list) list.push(item);
      else groups.set(key, [item]);
    }
    return [...groups.entries()];
  }, [stored.data]);

  const prereq = prerequisiteFor(generate.error, 'JOB_SEEKER') ?? prerequisiteFor(stored.error, 'JOB_SEEKER');
  const hasExplanations = items.some((i) => i.explanation ?? i.targetedSkillName);

  async function handleGenerate() {
    const next = await generate.run(token);
    if (next) stored.setData(next);
  }

  return (
    <AppShell>
      <PageHeader
        title="Course recommendations"
        lede="Online courses picked to close the gaps in your skill profile. Every one comes from a curated catalogue, so none of these links are invented."
        action={
          <button
            type="button"
            className="button button--primary button--auto"
            onClick={() => void handleGenerate()}
            disabled={generate.running}
          >
            {generate.running ? 'Finding courses…' : items.length ? 'Regenerate' : 'Find courses'}
          </button>
        }
      />

      {generate.failed && !prereq && <Banner message={messageFor(generate.error)} />}
      {prereq && <PrerequisiteState to={prereq.to} message={prereq.message} />}

      {(stored.loading || generate.running) && <Skeleton rows={4} />}

      {!stored.loading && !generate.running && stored.failed && !prereq && (
        <ErrorState message={messageFor(stored.error)} onRetry={stored.reload} />
      )}

      {!stored.loading && !generate.running && !prereq && !stored.failed && (
        <>
          {items.length === 0 ? (
            <EmptyState
              title="No recommendations yet"
              body="Generate a set and they will be matched to the skills you are weakest at. You need a confirmed transcript first, so the system knows what those are."
            />
          ) : (
            <>
              {!hasExplanations && (
                <p className="notice notice--info">
                  These are your previously saved recommendations. Which skill each one targets
                  is not stored with them — <strong>regenerate</strong> to see that and the
                  reasoning again, refreshed against your current gaps.
                </p>
              )}

              <div className="stack">
                {grouped.map(([skill, courses]) => (
                  <section key={skill}>
                    {skill !== UNGROUPED && (
                      <h2 className="section__title">
                        {skill}
                        <span className="section__count">{courses.length}</span>
                      </h2>
                    )}
                    <ul className="grid list-reset">
                      {courses.map((course) => (
                        <Card as="li" key={course.recommendationId} className="course">
                          <h3 className="course__name">{course.courseName}</h3>
                          {course.explanation && (
                            <p className="course__why">{course.explanation}</p>
                          )}
                          <div className="course__foot">
                            <span className="cell__quiet">
                              {formatDate(course.recommendedAt)}
                            </span>
                            <a
                              className="button button--secondary button--small button--auto"
                              href={course.sourceLink}
                              target="_blank"
                              rel="noreferrer noopener"
                            >
                              View course
                            </a>
                          </div>
                        </Card>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </AppShell>
  );
}
