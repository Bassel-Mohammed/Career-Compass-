import type {
  DraftSkillDecision,
  DraftSkillResponse,
  LearningOutcomeExtractionStatus,
} from '../../types';

export const RUNNING_STATUSES: readonly LearningOutcomeExtractionStatus[] = [
  'UPLOADED',
  'QUEUED',
  'EXTRACTING',
  'PUBLISHING',
];

export function isRunningStatus(status: LearningOutcomeExtractionStatus): boolean {
  return RUNNING_STATUSES.includes(status);
}

export function statusLabel(status: LearningOutcomeExtractionStatus): string {
  const labels: Record<LearningOutcomeExtractionStatus, string> = {
    UPLOADED: 'Uploaded',
    QUEUED: 'Queued',
    EXTRACTING: 'Extracting skills',
    READY_FOR_REVIEW: 'Ready for review',
    PUBLISHING: 'Publishing',
    PUBLISHED: 'Published',
    FAILED: 'Extraction failed',
    CANCELLED: 'Cancelled',
  };
  return labels[status];
}

export function statusTone(
  status: LearningOutcomeExtractionStatus,
): 'ok' | 'warn' | 'danger' | 'neutral' | 'working' {
  if (status === 'PUBLISHED' || status === 'READY_FOR_REVIEW') return 'ok';
  if (status === 'FAILED') return 'danger';
  if (status === 'CANCELLED') return 'neutral';
  if (status === 'UPLOADED' || status === 'QUEUED' || status === 'EXTRACTING') return 'working';
  return 'warn';
}

export function decisionLabel(decision: DraftSkillDecision): string {
  const labels: Record<DraftSkillDecision, string> = {
    PENDING: 'Pending',
    ACCEPTED: 'Accepted',
    REPLACED: 'Replaced',
    REMOVED: 'Removed',
    ADDED: 'Added',
  };
  return labels[decision];
}

export function activeDraftSkills(skills: DraftSkillResponse[]): DraftSkillResponse[] {
  return skills.filter((skill) => skill.decision !== 'REMOVED');
}

export function duplicateCanonicalIds(skills: DraftSkillResponse[]): Set<string> {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const skill of activeDraftSkills(skills)) {
    if (!skill.canonicalSkillId) continue;
    if (seen.has(skill.canonicalSkillId)) duplicates.add(skill.canonicalSkillId);
    seen.add(skill.canonicalSkillId);
  }
  return duplicates;
}

/**
 * Where a row sits in the review queue. Publish blockers surface first, terms
 * that need human judgment next, and rubber-stamp accepts last. Never rank by
 * raw matchScore across groups — the per-scorer thresholds exist precisely so
 * one number cannot be compared globally.
 */
export type ReviewPriority = 'blocked' | 'judgment' | 'quick' | 'archived';

const REVIEW_PRIORITY_ORDER: readonly ReviewPriority[] = [
  'blocked',
  'judgment',
  'quick',
  'archived',
];

export function reviewPriority(skill: DraftSkillResponse): ReviewPriority {
  if (skill.decision === 'REMOVED') return 'archived';
  if (!skill.canonicalSkillId) return 'blocked';
  if (skill.decision === 'PENDING' && skill.aiReviewStatus === 'needs_review') return 'judgment';
  return 'quick';
}

/**
 * Gap between the top two matcher scores, from the candidates already on the
 * row. A small margin means the matcher nearly tied, so the term is genuinely
 * ambiguous. No comparable scores means maximum uncertainty.
 */
function decisionMargin(skill: DraftSkillResponse): number {
  const scores = [
    ...(typeof skill.matchScore === 'number' ? [skill.matchScore] : []),
    ...skill.candidates.map((candidate) => candidate.score),
  ].sort((a, b) => b - a);
  return scores.length >= 2 ? Math.max(0, scores[0] - scores[1]) : 0;
}

function compareByTerm(a: DraftSkillResponse, b: DraftSkillResponse): number {
  return a.term.localeCompare(b.term) || a.draftSkillId - b.draftSkillId;
}

const GROUP_COMPARATORS: Record<ReviewPriority, (a: DraftSkillResponse, b: DraftSkillResponse) => number> = {
  blocked: (a, b) => b.evidenceCount - a.evidenceCount || compareByTerm(a, b),
  judgment: (a, b) =>
    decisionMargin(a) - decisionMargin(b) ||
    (a.matchScore ?? 0) - (b.matchScore ?? 0) ||
    b.evidenceCount - a.evidenceCount ||
    compareByTerm(a, b),
  quick: (a, b) =>
    (b.matchScore ?? -1) - (a.matchScore ?? -1) ||
    b.evidenceCount - a.evidenceCount ||
    compareByTerm(a, b),
  archived: (a, b) => b.updatedAt.localeCompare(a.updatedAt) || compareByTerm(a, b),
};

/** Keep rows sharing a canonical skill adjacent; first appearance sets cluster order. */
function clusterAdjacent(rows: DraftSkillResponse[]): DraftSkillResponse[] {
  const clusters = new Map<string | symbol, DraftSkillResponse[]>();
  for (const row of rows) {
    const key: string | symbol = row.canonicalSkillId ?? Symbol('unmatched');
    const bucket = clusters.get(key);
    if (bucket) bucket.push(row);
    else clusters.set(key, [row]);
  }
  return [...clusters.values()].flat();
}

/**
 * Reviewer-priority order: unresolved blockers → judgment calls (lowest
 * margin first) → high-confidence accepts → removed rows. Duplicate canonical
 * skills end up adjacent inside their group so collisions are visible during
 * review instead of at publish.
 */
export function sortDraftSkillsForReview(skills: DraftSkillResponse[]): DraftSkillResponse[] {
  const groups = new Map<ReviewPriority, DraftSkillResponse[]>(
    REVIEW_PRIORITY_ORDER.map((priority) => [priority, []]),
  );
  for (const skill of skills) groups.get(reviewPriority(skill))!.push(skill);
  return REVIEW_PRIORITY_ORDER.flatMap((priority) =>
    clusterAdjacent(groups.get(priority)!.sort(GROUP_COMPARATORS[priority])),
  );
}

/**
 * Hold positions stable while the reviewer works: keep every known row where
 * it was, and let brand-new drafts join at the end until a manual re-sort.
 */
export function mergeReviewOrder(previous: number[], next: DraftSkillResponse[]): number[] {
  const present = new Set(next.map((row) => row.draftSkillId));
  const kept = previous.filter((id) => present.has(id));
  const known = new Set(kept);
  const appended = next.filter((row) => !known.has(row.draftSkillId)).map((row) => row.draftSkillId);
  return [...kept, ...appended];
}

