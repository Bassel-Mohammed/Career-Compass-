import type {
  BandCounts,
  CareerPathSkill,
  DemandBand,
  SkillLevelResponse,
} from '../../types';
import { normalise } from '../../components/status';

/**
 * Presentation logic for the skill dashboard. No JSX, so it can be reasoned about — and
 * corrected — without rendering anything. Mirrors `pages/content/workflow.ts`.
 *
 * The one rule worth stating: **bands are never computed here.** They arrive on the wire from
 * the AI service, which owns the job-posting data the thresholds are derived from. A second
 * definition of "critical" in the frontend would be the two disagreeing the first time either
 * moved, and the disagreement would be invisible.
 */

/** Most-demanded first. Every list on the page is ordered by this. */
export const BAND_ORDER: readonly DemandBand[] = ['critical', 'important', 'useful'];

interface BandMeta {
  /** What the band is called on screen. */
  label: string;
  /**
   * What it means, in the student's terms rather than the model's. Rendered next to the label
   * everywhere the band appears: the colour of a chip is never the only thing carrying the
   * meaning (NFR-USE-05).
   */
  blurb: string;
  /** Longer form for the definitions block. */
  detail: string;
  tone: 'danger' | 'warn' | 'neutral';
}

export const BAND_META: Record<DemandBand, BandMeta> = {
  critical: {
    label: 'Critical',
    blurb: 'at least 1 posting in 4',
    detail:
      'Asked for by 25% or more of the job postings on this path. These are what employers '
      + 'treat as the baseline — learn these first.',
    tone: 'danger',
  },
  important: {
    label: 'Important',
    blurb: 'between 1 in 10 and 1 in 4',
    detail:
      'Asked for by 10% to 25% of postings. Not universal, but common enough that having them '
      + 'opens up noticeably more roles.',
    tone: 'warn',
  },
  useful: {
    label: 'Useful',
    blurb: 'fewer than 1 posting in 10',
    detail:
      'Asked for by under 10% of postings. Worth having once the bands above are covered — '
      + 'these are what separate similar candidates rather than what gets you considered.',
    tone: 'neutral',
  },
};

const EMPTY_COUNTS: BandCounts = { strong: 0, moderate: 0, weak: 0, total: 0 };

/** A skill the student meets the target for. */
export function isMet(skill: SkillLevelResponse): boolean {
  return normalise(skill.classification) === 'Strong';
}

export function isSoft(skill: { skillType?: string }): boolean {
  return skill.skillType === 'soft';
}

/**
 * Split technical from soft.
 *
 * Soft skills top nearly every career path, which is an accurate reading of job postings and
 * useless as advice: ranked in with the rest they give every student the same three suggestions
 * regardless of what they studied. The service already ranks them last; this lets the page hide
 * them entirely.
 */
export function splitSoft<T extends { skillType?: string }>(skills: T[]): {
  technical: T[];
  soft: T[];
} {
  return {
    technical: skills.filter((skill) => !isSoft(skill)),
    soft: skills.filter(isSoft),
  };
}

/** Group by band, preserving the order the service sent within each band. */
export function groupByBand<T extends { demandBand?: DemandBand }>(
  skills: T[],
): Record<DemandBand, T[]> {
  const groups: Record<DemandBand, T[]> = { critical: [], important: [], useful: [] };
  for (const skill of skills) {
    // A row with no band predates the field or came from a service that does not send it.
    // Treated as `useful` rather than dropped: a missing label is not a reason to hide a
    // requirement from the person it applies to.
    groups[skill.demandBand ?? 'useful'].push(skill);
  }
  return groups;
}

/**
 * Classification counts per band, over exactly the skills passed in.
 *
 * Counted from the rows on screen rather than read from the service's own `bandSummary`, because
 * the page can hide soft skills and the service cannot know that. Taking the service's totals
 * while the list below them is filtered puts "Critical 10" above a list of seven, which reads as
 * a bug in the page. One pool, one set of numbers.
 *
 * `bandSummary` still arrives on the wire and still describes what the service returned; it is
 * simply not the right denominator once the reader has filtered.
 */
export function bandReadiness(skills: SkillLevelResponse[]): Record<DemandBand, BandCounts> {
  const counted: Record<DemandBand, BandCounts> = {
    critical: { ...EMPTY_COUNTS },
    important: { ...EMPTY_COUNTS },
    useful: { ...EMPTY_COUNTS },
  };

  for (const skill of skills) {
    const bucket = counted[skill.demandBand ?? 'useful'];
    const classification = normalise(skill.classification);
    if (classification === 'Strong') bucket.strong += 1;
    else if (classification === 'Moderate') bucket.moderate += 1;
    else bucket.weak += 1;
    bucket.total += 1;
  }
  return counted;
}

/**
 * The gaps worth acting on first.
 *
 * The service already ordered by priority, so this filters rather than re-ranks. Soft skills are
 * excluded for the reason given on {@link splitSoft}.
 */
export function topPriority(skills: SkillLevelResponse[], limit = 6): SkillLevelResponse[] {
  return skills.filter((skill) => !isMet(skill) && !isSoft(skill)).slice(0, limit);
}

/** What the student already has, strongest first — so the page is not only a list of failures. */
export function strengths(skills: SkillLevelResponse[], limit = 8): SkillLevelResponse[] {
  return skills
    .filter(isMet)
    .slice()
    .sort((a, b) => (b.importancePercent ?? 0) - (a.importancePercent ?? 0))
    .slice(0, limit);
}

/**
 * The evidence behind a demand percentage, as a sentence.
 *
 * "asked for in 72 of 184 postings" rather than "39%": the count is what makes the number
 * checkable, and a student has no reason to trust a percentage with nothing under it. Degrades
 * to the percentage alone when the denominator is missing, and to nothing when both are.
 */
export function evidenceLine(
  skill: { postingCount?: number; importancePercent?: number; coveragePercent?: number },
  sampleSize?: number,
): string | null {
  const percent = skill.importancePercent ?? skill.coveragePercent;
  if (skill.postingCount != null && sampleSize) {
    return `Asked for in ${skill.postingCount} of ${sampleSize} job postings`;
  }
  if (percent == null) return null;
  return `Asked for in ${Math.round(percent)}% of job postings`;
}

/** How many of the critical requirements the student meets — the headline number. */
export function criticalProgress(
  readiness: Record<DemandBand, BandCounts>,
): { met: number; total: number } {
  return { met: readiness.critical.strong, total: readiness.critical.total };
}

/** Market rows carry `coveragePercent`; gap rows carry `importancePercent`. One accessor. */
export function demandPercent(
  skill: { importancePercent?: number; coveragePercent?: number },
): number {
  return skill.importancePercent ?? skill.coveragePercent ?? 0;
}

/** `2026-08-07T22:51:27Z` → `August 2026`. Returns null rather than guessing at a bad value. */
export function capturedMonth(iso?: string): string | null {
  if (!iso) return null;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return null;
  return when.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

/** Band totals for the market view, which reports them separately from the rows it returns. */
export function marketBandTotals(
  skills: CareerPathSkill[],
  supplied?: Partial<Record<DemandBand, number>>,
): Record<DemandBand, number> {
  const totals: Record<DemandBand, number> = { critical: 0, important: 0, useful: 0 };
  if (supplied && Object.keys(supplied).length > 0) {
    for (const band of BAND_ORDER) totals[band] = supplied[band] ?? 0;
    return totals;
  }
  for (const skill of skills) totals[skill.demandBand ?? 'useful'] += 1;
  return totals;
}
