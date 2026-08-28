import { Suspense, lazy } from 'react';
import { useMemo } from 'react';
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
const MarketBandChart = lazy(() => import('../../components/charts').then(m => ({ default: m.MarketBandChart })));
import { useAuth } from '../../auth/useAuth';
import { useAsync } from '../../hooks/useAsync';
import * as transcriptApi from '../../api/transcript';
import { formatPercent } from '../../api/format';
import { messageFor, prerequisiteFor } from '../../api/errors';
import type {
  CareerPathSkill,
  CareerPathSkillsResponse,
  SkillDashboardResponse,
  SkillLevelResponse,
  SkippedCourseResponse,
} from '../../types';
import {
  BAND_META,
  BAND_ORDER,
  capturedMonth,
  demandPercent,
  evidenceLine,
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

function SkillProfile({ data }: { data: SkillDashboardResponse }) {
  const { technical, soft } = useMemo(() => splitSoft(data.skills), [data.skills]);
  const openGaps = technical.filter((skill) => !isMet(skill)).length;
  const strongCount = technical.filter(isMet).length;
  const month = capturedMonth(data.marketCapturedAt);
  const priorities = useMemo(() => topPriority(technical, 5), [technical]);
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
      <Card className="skill-overview">
        <p className="skill-overview__eyebrow">Your readiness for {data.careerPathTitle}</p>
        <p className="skill-overview__score">{formatPercent(data.overallReadinessPercent)}</p>
        <ProgressBar
          value={data.overallReadinessPercent}
          label={`Overall readiness for ${data.careerPathTitle}`}
        />
        <div className="grid grid--stats skill-overview__stats">
          <Stat label="Strong skills" value={strongCount} hint="already at the target" />
          <Stat label="Skills to improve" value={openGaps} hint="below the target" />
          <Stat label="Courses used" value={data.coursesCounted ?? 0} hint="from your transcript" />
        </div>
        <Link className="button button--primary button--auto" to="/courses">
          View recommended courses
        </Link>
      </Card>

      {priorities.length > 0 && (
        <Card as="section">
          <h2 className="section__title">
            Skills to improve first
            <span className="section__count">{priorities.length}</span>
          </h2>
          <p className="section__lede">
            Start here. These are the most useful gaps to close for {data.careerPathTitle}.
          </p>
          <ul className="list-reset skills">
            {priorities.map((skill) => (
              <SkillRow key={skill.canonicalSkillId ?? skill.skillName} skill={skill}
                        sampleSize={data.sampleSize} showActions />
            ))}
          </ul>
        </Card>
      )}

      {held.length > 0 && (
        <Card as="section">
          <h2 className="section__title">
            Your strong skills
            <span className="section__count">{strongCount}</span>
          </h2>
          <p className="section__lede">These are supported by your courses or quiz results.</p>
          <ul className="list-reset skills">
            {held.map((skill) => (
              <SkillRow key={skill.canonicalSkillId ?? skill.skillName} skill={skill}
                        sampleSize={data.sampleSize} />
            ))}
          </ul>
        </Card>
      )}

      <Card as="section">
        <details className="dashboard-details">
          <summary>Show all skills and how this dashboard was calculated</summary>
          <p className="section__lede">
            Course codes come from your confirmed transcript. A skill appears when an extracted
            course syllabus says that course teaches it. The score uses your grade, or your latest
            quiz result when one exists. Career requirements come from job postings.
          </p>
          {soft.length > 0 && (
            <p className="skills__evidence">
              {soft.length} soft skill{soft.length === 1 ? '' : 's'} are included in the full list
              but kept out of your learn-first suggestions.
            </p>
          )}
          <Provenance
            careerPath={data.careerPathTitle}
            sampleSize={data.sampleSize}
            month={month}
            basedOnQuizResults={data.basedOnQuizResults}
            coursesCounted={data.coursesCounted}
            coursesSkipped={data.coursesSkipped}
            syntheticCounted={data.syntheticCounted}
          />
          <ul className="list-reset skills dashboard-details__skills">
            {data.skills.map((skill) => (
              <SkillRow key={skill.canonicalSkillId ?? skill.skillName} skill={skill}
                        sampleSize={data.sampleSize} />
            ))}
          </ul>
        </details>
      </Card>
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

function SkillRow({
  skill,
  sampleSize,
  showActions = false,
}: {
  skill: SkillLevelResponse;
  sampleSize?: number;
  showActions?: boolean;
}) {
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
        Current {formatPercent(skill.score)}
        {skill.targetScore != null && ` · target ${formatPercent(skill.targetScore)}`}
        {evidence && ` · ${evidence}`}
      </p>

      <SkillSourceGuide skill={skill} />

      {showActions && skill.canonicalSkillId && !met && (
        <div className="skills__actions">
          <Link
            className="skills__action"
            to={`/quizzes?skill=${encodeURIComponent(skill.canonicalSkillId)}&name=${encodeURIComponent(skill.skillName ?? '')}`}
          >
            Take a quiz to refine this
          </Link>
          <Link className="skills__action" to="/courses">
            Find a course
          </Link>
        </div>
      )}
    </li>
  );
}

function SkillSourceGuide({ skill }: { skill: SkillLevelResponse }) {
  const courses = skill.sourceCourses ?? [];
  const usesQuiz = skill.evidenceSource === 'quizzes' || skill.evidenceSource === 'grades+quizzes';

  if (courses.length === 0) {
    return (
      <p className="skill-source skill-source--empty">
        {usesQuiz
          ? 'Source: your completed skill quiz.'
          : 'No supporting course was found in your transcript. This skill is shown because your career path asks for it.'}
      </p>
    );
  }

  return (
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
