import { Suspense, lazy } from 'react';
import { useMemo, useState } from 'react';
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
const GapChart = lazy(() => import('../../components/charts').then(m => ({ default: m.GapChart })));
const MarketBandChart = lazy(() => import('../../components/charts').then(m => ({ default: m.MarketBandChart })));
const TierSplitChart = lazy(() => import('../../components/charts').then(m => ({ default: m.TierSplitChart })));
import type { GapDatum, TierDatum } from '../../components/charts';
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as transcriptApi from '../../api/transcript';
import { formatPercent } from '../../api/format';
import { messageFor, prerequisiteFor } from '../../api/errors';
import type {
  CareerPathSkill,
  CareerPathSkillsResponse,
  DemandBand,
  SkillDashboardResponse,
  SkillLevelResponse,
  SkippedCourseResponse,
} from '../../types';
import {
  BAND_META,
  BAND_ORDER,
  bandReadiness,
  capturedMonth,
  criticalProgress,
  demandPercent,
  evidenceLine,
  groupByBand,
  isMet,
  marketBandTotals,
  splitSoft,
  strengths,
  topPriority,
} from './dashboard';

/**
 * FR-JS-14 and FR-JS-21 — the home screen once a student is set up.
 *
 * Recomputed by the backend on every visit rather than read from a cache, so it always reflects
 * the latest grades, career path and quiz results, and always costs an AI round trip. Hence the
 * skeleton rather than an empty flash (NFR-USE-04).
 *
 * The page is organised around **how much the job market asks for each skill**, not around the
 * student's scores. Ordering by score alone put every unstudied skill at the top in arbitrary
 * order — a list of everything not done rather than what to do next — so the service ranks by
 * demand-weighted shortfall and this groups by the band that demand falls into.
 */
export function DashboardPage() {
  const { session } = useAuth();
  const token = session!.token;
  const dashboard = useAsync(() => transcriptApi.getSkillDashboard(token), [token]);

  const prereq = prerequisiteFor(dashboard.error, 'JOB_SEEKER');
  const data = dashboard.data;

  // A student with no transcript still has a career path, and what that career asks for is
  // answerable without knowing anything about them. Requested only when the gap could not be
  // built for want of a transcript, so the normal path still costs one round trip.
  const marketOnly = !dashboard.loading && !data && prereq?.to === '/transcript';
  const market = useAsync<CareerPathSkillsResponse | null>(
    () => (marketOnly ? transcriptApi.getCareerPathSkills(token) : Promise.resolve(null)),
    [token, marketOnly],
  );

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

      {dashboard.loading && <Skeleton rows={6} />}

      {!dashboard.loading && prereq && (
        <div className="stack">
          {market.data && <MarketPreview market={market.data} />}
          <PrerequisiteState to={prereq.to} message={prereq.message} />
        </div>
      )}

      {!dashboard.loading && dashboard.failed && !prereq && (
        <ErrorState message={messageFor(dashboard.error)} onRetry={dashboard.reload} />
      )}

      {!dashboard.loading && data && <SkillProfile data={data} />}
    </AppShell>
  );
}

/* ===========================================================================
   The profile, once a transcript exists
   =========================================================================== */

type Filter = DemandBand | 'all' | 'gaps';

function SkillProfile({ data }: { data: SkillDashboardResponse }) {
  const [filter, setFilter] = useState<Filter>('all');
  const [showSoft, setShowSoft] = useState(false);
  const { technical, soft } = useMemo(() => splitSoft(data.skills), [data.skills]);
  const pool = showSoft ? data.skills : technical;
  const readiness = useMemo(() => bandReadiness(pool), [pool]);
  const critical = criticalProgress(readiness);
  const openGaps = pool.filter((skill) => !isMet(skill)).length;
  const month = capturedMonth(data.marketCapturedAt);

  const tierData: TierDatum[] = BAND_ORDER.map((band) => ({
    band,
    label: BAND_META[band].label,
    ...readiness[band],
  }));

  const priorities = useMemo(() => topPriority(technical, 6), [technical]);
  const gapData: GapDatum[] = priorities.map((skill) => {
    const target = skill.targetScore ?? 100;
    const current = Math.min(skill.score, target);
    return {
      label: skill.skillName ?? 'Unnamed skill',
      current,
      shortfall: Math.max(0, target - current),
      target,
      band: skill.demandBand ?? 'useful',
    };
  });

  const visible = useMemo(() => {
    if (filter === 'all') return pool;
    if (filter === 'gaps') return pool.filter((skill) => !isMet(skill));
    return pool.filter((skill) => (skill.demandBand ?? 'useful') === filter);
  }, [pool, filter]);

  const grouped = useMemo(() => groupByBand(visible), [visible]);
  const held = useMemo(() => strengths(technical), [technical]);

  if (data.skills.length === 0) {
    return (
      <Card>
        <p className="cell__quiet">
          No skills could be derived from your courses yet. This usually means the courses on your
          transcript have no extracted syllabus behind them.
        </p>
      </Card>
    );
  }

  return (
    <div className="stack">
      <Provenance
        careerPath={data.careerPathTitle}
        sampleSize={data.sampleSize}
        month={month}
        basedOnQuizResults={data.basedOnQuizResults}
        coursesCounted={data.coursesCounted}
        coursesSkipped={data.coursesSkipped}
        syntheticCounted={data.syntheticCounted}
      />

      <div className="grid grid--stats">
        <Stat
          label="Overall readiness"
          value={formatPercent(data.overallReadinessPercent)}
          hint={`for ${data.careerPathTitle}`}
        />
        <Stat
          label="Critical skills met"
          value={`${critical.met} of ${critical.total}`}
          hint="what employers treat as the baseline"
        />
        <Stat label="Open gaps" value={openGaps} hint="skills below the level asked for" />
        <Stat
          label="Skills measured"
          value={pool.length}
          hint={
            showSoft || soft.length === 0
              ? 'against this career path'
              : `${soft.length} soft skill${soft.length === 1 ? '' : 's'} hidden`
          }
        />
      </div>

      <Card>
        <h2 className="section__title">Readiness for {data.careerPathTitle}</h2>
        <ProgressBar
          value={data.overallReadinessPercent}
          label={`Overall readiness for ${data.careerPathTitle}`}
        />
      </Card>

      <Card as="section">
        <h2 className="section__title">What this career actually asks for</h2>
        <p className="section__lede">
          Every skill below is placed by how many real job postings for {data.careerPathTitle}
          {' '}asked for it. Work down from the top: the first band is what employers treat as the
          baseline.
          {!showSoft && soft.length > 0 && (
            <> Soft skills are excluded from these counts — turn them on under “All skills”.</>
          )}
        </p>
        <Suspense fallback={<Skeleton />}><TierSplitChart data={tierData} /></Suspense>
        <dl className="bands">
          {BAND_ORDER.map((band) => (
            <div key={band} className="bands__row">
              <dt>
                <span className={`tier-chip tier-chip--${band}`}>{BAND_META[band].label}</span>
                <span className="bands__blurb">{BAND_META[band].blurb}</span>
              </dt>
              <dd>
                <span className="bands__count">
                  {readiness[band].total} skill{readiness[band].total === 1 ? '' : 's'}
                </span>
                {' — '}
                {readiness[band].strong} strong · {readiness[band].moderate} partly there ·{' '}
                {readiness[band].weak} missing
                <p className="bands__detail">{BAND_META[band].detail}</p>
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      {priorities.length > 0 && (
        <Card as="section">
          <h2 className="section__title">
            Learn these first
            <span className="section__count">{priorities.length}</span>
          </h2>
          <p className="section__lede">
            Ranked by what closing each gap is worth — a small shortfall in something most
            postings ask for beats a large one in something almost nobody does.
          </p>
          <Suspense fallback={<Skeleton />}><GapChart data={gapData} /></Suspense>
          <ul className="list-reset skills">
            {priorities.map((skill) => (
              <SkillRow key={skill.canonicalSkillId ?? skill.skillName} skill={skill}
                        sampleSize={data.sampleSize} />
            ))}
          </ul>
        </Card>
      )}

      <Card as="section">
        <div className="section-heading section-heading--wrap">
          <h2 className="section__title">
            All skills
            <span className="section__count">{visible.length}</span>
          </h2>
          <div className="section-heading__actions">
            <label className="soft-toggle">
              <input
                type="checkbox"
                checked={showSoft}
                onChange={(event) => setShowSoft(event.target.checked)}
              />
              Include soft skills
            </label>
          </div>
        </div>

        <div className="review-filters" role="group" aria-label="Filter skills by demand">
          <FilterChip active={filter === 'all'} onClick={() => setFilter('all')}>
            All
          </FilterChip>
          {BAND_ORDER.map((band) => (
            <FilterChip key={band} active={filter === band} onClick={() => setFilter(band)}>
              {BAND_META[band].label} ({readiness[band].total})
            </FilterChip>
          ))}
          <FilterChip active={filter === 'gaps'} onClick={() => setFilter('gaps')}>
            Gaps only ({openGaps})
          </FilterChip>
        </div>

        {visible.length === 0 ? (
          <p className="cell__quiet">Nothing in this band yet.</p>
        ) : (
          BAND_ORDER.filter((band) => grouped[band].length > 0).map((band) => (
            <section key={band} className="band-group" aria-label={`${BAND_META[band].label} skills`}>
              <h3 className="band-group__title">
                <span className={`tier-chip tier-chip--${band}`}>{BAND_META[band].label}</span>
                <span className="bands__blurb">{BAND_META[band].blurb}</span>
                <span className="section__count">{grouped[band].length}</span>
              </h3>
              <ul className="list-reset skills">
                {grouped[band].map((skill) => (
                  <SkillRow key={skill.canonicalSkillId ?? skill.skillName} skill={skill}
                            sampleSize={data.sampleSize} />
                ))}
              </ul>
            </section>
          ))
        )}
      </Card>

      {held.length > 0 && (
        <Card as="section">
          <h2 className="section__title">
            Already at the level asked for
            <span className="section__count">{held.length}</span>
          </h2>
          <ul className="list-reset strengths">
            {held.map((skill) => (
              <li key={skill.canonicalSkillId ?? skill.skillName} className="strengths__item">
                <span className="skills__name">{skill.skillName}</span>
                <StatusBadge status={skill.classification} />
                <span className="skills__evidence">
                  {evidenceLine(skill, data.sampleSize) ?? ''}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/* ===========================================================================
   Pieces
   =========================================================================== */

function Provenance({
  careerPath,
  sampleSize,
  month,
  basedOnQuizResults,
  coursesCounted,
  coursesSkipped,
  syntheticCounted,
}: {
  careerPath: string;
  sampleSize?: number;
  month: string | null;
  basedOnQuizResults: boolean;
  coursesCounted?: number;
  coursesSkipped?: SkippedCourseResponse[];
  syntheticCounted?: number;
}) {
  const unreadable = (coursesSkipped ?? []).filter(
    (course) => course.reason === 'no skill map',
  );
  const notPassed = (coursesSkipped ?? []).filter((course) => course.reason !== 'no skill map');
  const total = (coursesCounted ?? 0) + (coursesSkipped?.length ?? 0);

  return (
    <Card className="provenance">
      <p className="provenance__line">
        <strong>{careerPath}</strong>
        {sampleSize ? (
          <>
            {' — '}measured against {sampleSize} real job postings
            {month ? ` collected in ${month}` : ''}.
          </>
        ) : (
          <> — measured against job postings for this career path.</>
        )}
      </p>
      {/* FR-JS-22: say plainly where the numbers came from. A dashboard built from grades alone
          is a weaker claim than one backed by quiz evidence, and the student cannot tell the
          difference by looking at it. */}
      <p className="notice notice--info">
        {basedOnQuizResults ? (
          <>
            <strong>Refined by your quiz results.</strong> Skills you have been quizzed on use
            that evidence instead of your grades.
          </>
        ) : (
          <>
            <strong>Estimated from your grades.</strong> You have not completed any quizzes yet —{' '}
            <Link to="/quizzes">take one</Link> to replace an estimate with evidence.
          </>
        )}
      </p>

      {/* A skill reads "missing" either because the student never studied it or because the
          course that teaches it has no syllabus extracted yet. Saying which is the difference
          between a fair result and one that blames them for our own missing data. */}
      {/* A div, not a p: <details>, <summary> and <ul> are all block content and are invalid
          inside a paragraph. The browser used to auto-close the <p> before them, which React
          flagged as a hydration hazard on every render of this page. */}
      {unreadable.length > 0 && (
        <div className="notice notice--warn">
          <p>
            <strong>
              Built from {coursesCounted} of your {total} courses.
            </strong>{' '}
            {unreadable.length} {unreadable.length === 1 ? 'course has' : 'courses have'} no
            syllabus extracted yet, so skills {unreadable.length === 1 ? 'it teaches' : 'they teach'}{' '}
            may show as missing here even if you studied them.
          </p>
          <details className="review-details">
            <summary>
              Which {unreadable.length === 1 ? 'course' : 'courses'}
            </summary>
            <ul className="list-reset skipped-courses">
              {unreadable.map((course) => (
                <li key={course.courseCode}>{course.courseCode}</li>
              ))}
            </ul>
          </details>
        </div>
      )}

      {notPassed.length > 0 && (
        <p className="skills__evidence">
          {notPassed.length} {notPassed.length === 1 ? 'course was' : 'courses were'} not passed
          and {notPassed.length === 1 ? 'carries' : 'carry'} no credit towards these skills.
        </p>
      )}

      {/* Synthetic coursework must never be presented as a real academic record. Every file in
          the demo corpus says "Not a real MEU document"; this is the product repeating it. */}
      {(syntheticCounted ?? 0) > 0 && (
        <p className="notice notice--preview">
          {/* Naming what is synthetic is only half of it. Without the second sentence a reader
              reasonably concludes the whole dashboard is invented, when the demand side — the
              job postings every skill is ranked against — is real data. */}
          <strong>Demo data.</strong> {syntheticCounted} of the {coursesCounted} courses behind
          this profile use synthetic syllabi generated for demonstration, not real university
          documents. The job-market figures they are measured against are real.
        </p>
      )}
    </Card>
  );
}

function SkillRow({ skill, sampleSize }: { skill: SkillLevelResponse; sampleSize?: number }) {
  const band = skill.demandBand ?? 'useful';
  const evidence = evidenceLine(skill, sampleSize);
  const met = isMet(skill);

  return (
    <li className="skills__row">
      <div className="skills__head">
        <span className="skills__name">{skill.skillName ?? 'Unnamed skill'}</span>
        <span className={`tier-chip tier-chip--${band}`}>{BAND_META[band].label}</span>
        <StatusBadge status={skill.classification} />
      </div>

      <ProgressBar
        value={skill.score}
        status={skill.classification}
        label={`${skill.skillName ?? 'Skill'} score`}
      />

      <p className="skills__evidence">
        {evidence}
        {skill.requiredLevel && (
          <>
            {evidence ? ' · ' : ''}Asked for at {skill.requiredLevel} level
          </>
        )}
        {skill.targetScore != null && ` · target ${formatPercent(skill.targetScore)}`}
      </p>

      {skill.explanation && <p className="skills__why">{skill.explanation}</p>}

      <div className="skills__actions">
        {skill.canonicalSkillId && !met && (
          <>
            <Link
              className="skills__action"
              to={`/quizzes?skill=${encodeURIComponent(skill.canonicalSkillId)}&name=${encodeURIComponent(skill.skillName ?? '')}`}
            >
              Take a quiz to refine this
            </Link>
            <Link className="skills__action" to="/courses">
              Find a course
            </Link>
          </>
        )}
        <SkillSourceGuide skill={skill} />
      </div>
    </li>
  );
}

function SkillSourceGuide({ skill }: { skill: SkillLevelResponse }) {
  const courses = skill.sourceCourses ?? [];
  const usesQuiz = skill.evidenceSource === 'quizzes' || skill.evidenceSource === 'grades+quizzes';

  if (courses.length === 0) {
    return (
      <details className="skill-source-menu">
        <summary className="skills__action">
          {usesQuiz ? 'Skill source' : 'Why this skill is shown'}
        </summary>
        <p className="skill-source skill-source--empty">
          {usesQuiz
            ? 'Source: your completed skill quiz.'
            : 'No supporting course was found in your transcript. This skill is shown because your career path asks for it.'}
        </p>
      </details>
    );
  }

  return (
    <details className="skill-source-menu">
      <summary className="skills__action">Where you developed this skill</summary>
      <div className="skill-source">
        <p className="skill-source__title">
          {usesQuiz ? 'Quiz score, supported by:' : 'You developed this skill in:'}
        </p>
        <ul className="list-reset skill-source__courses">
          {courses.map((course, index) => (
            <li key={`${course.courseCode ?? 'course'}-${index}`}>
              <strong>{course.courseCode ?? 'Course'}</strong>
              {course.courseName && ` — ${course.courseName}`}
              {course.grade && <span className="skill-source__meta">Grade {course.grade}</span>}
              {course.level && <span className="skill-source__meta">{course.level} syllabus level</span>}
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`review-filter${active ? ' review-filter--active' : ''}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

/* ===========================================================================
   Before a transcript exists

   The market on its own. Real posting counts, no student data — so the page has something true
   to say to somebody who has not uploaded anything yet.
   =========================================================================== */

function MarketPreview({ market }: { market: CareerPathSkillsResponse }) {
  const totals = marketBandTotals(market.skills, market.bandTotals);
  const month = capturedMonth(market.capturedAt);
  const { technical } = splitSoft(market.skills);
  const topCritical = technical.filter((skill) => skill.demandBand === 'critical').slice(0, 8);

  return (
    <Card as="section">
      <h2 className="section__title">What {market.careerPath} asks for</h2>
      <p className="section__lede">
        Derived from {market.sampleSize ?? 'the'} real job postings
        {month ? ` collected in ${month}` : ''}. Upload your transcript to see where you already
        stand against them.
      </p>

      <Suspense fallback={<Skeleton />}>
        <MarketBandChart
        data={BAND_ORDER.map((band) => ({
          band,
          label: BAND_META[band].label,
          count: totals[band],
        }))}
      />
      </Suspense>

      {topCritical.length > 0 && (
        <>
          <h3 className="band-group__title">
            <span className="tier-chip tier-chip--critical">Critical</span>
            <span className="bands__blurb">{BAND_META.critical.blurb}</span>
          </h3>
          <ul className="list-reset skills">
            {topCritical.map((skill) => (
              <MarketRow key={skill.skillId} skill={skill} sampleSize={market.sampleSize} />
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function MarketRow({ skill, sampleSize }: { skill: CareerPathSkill; sampleSize?: number }) {
  return (
    <li className="skills__row">
      <div className="skills__head">
        <span className="skills__name">{skill.label}</span>
        <span className={`tier-chip tier-chip--${skill.demandBand}`}>
          {BAND_META[skill.demandBand].label}
        </span>
      </div>
      {/* The market track is demand, not attainment — a different quantity from the score bars
          elsewhere on this page, which is why it carries its own label rather than reusing the
          Strong/Moderate/Weak colouring. */}
      <ProgressBar
        value={demandPercent(skill)}
        label={`Share of postings asking for ${skill.label}`}
      />
      <p className="skills__evidence">
        {evidenceLine(skill, sampleSize)}
        {skill.requiredLevel && ` · asked for at ${skill.requiredLevel} level`}
      </p>
    </li>
  );
}
