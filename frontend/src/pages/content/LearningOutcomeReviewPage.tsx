import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError } from '../../api/client';
import * as contentManagerApi from '../../api/contentManager';
import { formatDate } from '../../api/format';
import { messageFor } from '../../api/errors';
import { useAuth } from '../../auth/useAuth';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Select } from '../../components/Select';
import { TextArea } from '../../components/TextArea';
import { TextField } from '../../components/TextField';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, Stat } from '../../components/ui';
import { useAsync } from '../../hooks/useAsync';
import type {
  DraftSkillDecision,
  DraftSkillResponse,
  SkillLevel,
  TaxonomySkillResponse,
  UpdateDraftSkillRequest,
} from '../../types';
import {
  activeDraftSkills,
  decisionLabel,
  duplicateCanonicalIds,
  isRunningStatus,
  mergeReviewOrder,
  reviewPriority,
  sortDraftSkillsForReview,
  statusLabel,
  statusTone,
} from './workflow';

const POLL_INTERVAL_MS = 3_000;
const LEVEL_OPTIONS = [
  { value: 'beginner', label: 'Beginner' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced' },
];

type Filter = 'ALL' | DraftSkillDecision;

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'ACCEPTED', label: 'Accepted' },
  { value: 'REPLACED', label: 'Replaced' },
  { value: 'ADDED', label: 'Added' },
  { value: 'REMOVED', label: 'Removed' },
];

function confidencePercent(value: number | undefined): string | null {
  if (value === undefined) return null;
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(Math.max(0, Math.min(100, percent)))}%`;
}

function evidenceText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const row = value as Record<string, unknown>;
    for (const key of ['text', 'snippet', 'sentence', 'rawText', 'raw_text', 'description']) {
      if (typeof row[key] === 'string') return row[key];
    }
    try {
      return JSON.stringify(value);
    } catch {
      return 'Structured extraction evidence';
    }
  }
  return String(value);
}

function TaxonomyPicker({
  token,
  disabled,
  disabledSkillIds,
  onChoose,
}: {
  token: string;
  disabled?: boolean;
  disabledSkillIds: Set<string>;
  onChoose: (skill: TaxonomySkillResponse) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<TaxonomySkillResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [searched, setSearched] = useState(false);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setError(new Error('Enter at least two characters to search the taxonomy.'));
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const response = await contentManagerApi.searchTaxonomySkills(token, trimmed);
      setResults(response.items);
      setTotal(response.total);
      setSearched(true);
    } catch (cause) {
      setError(cause);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="taxonomy-picker">
      <form className="taxonomy-search" role="search" onSubmit={search}>
        <TextField
          label="Search the canonical skill taxonomy"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. data structures"
          disabled={disabled || searching}
        />
        <button
          type="submit"
          className="button button--secondary button--auto"
          disabled={disabled || searching || query.trim().length < 2}
        >
          {searching ? 'Searching…' : 'Search'}
        </button>
      </form>
      {error != null && <Banner message={messageFor(error)} />}
      {searched && results.length === 0 && (
        <p className="cell__quiet" role="status">
          No canonical skills match “{query.trim()}”. Try a broader term.
        </p>
      )}
      {results.length > 0 && (
        <div>
          <p className="taxonomy-results__count" role="status">
            Showing {results.length} of {total} result{total === 1 ? '' : 's'}
          </p>
          <ul className="taxonomy-results list-reset" aria-label="Canonical skill search results">
            {results.map((skill) => {
              const unavailable = disabledSkillIds.has(skill.skillId);
              return (
                <li key={skill.skillId}>
                  <button
                    type="button"
                    className="taxonomy-result"
                    onClick={() => onChoose(skill)}
                    disabled={disabled || unavailable}
                  >
                    <span>
                      <strong>{skill.label}</strong>
                      <small>
                        {[skill.skillType, skill.source].filter(Boolean).join(' · ') || skill.skillId}
                      </small>
                    </span>
                    <span>{unavailable ? 'Already in draft' : 'Choose'}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function SkillDraftCard({
  skill,
  token,
  duplicate,
  readOnly,
  busy,
  unavailableReplacementIds,
  onSave,
  onReplace,
  onDelete,
}: {
  skill: DraftSkillResponse;
  token: string;
  duplicate: boolean;
  readOnly: boolean;
  busy: boolean;
  unavailableReplacementIds: Set<string>;
  onSave: (skill: DraftSkillResponse, changes: Omit<UpdateDraftSkillRequest, 'expectedRowVersion' | 'expectedDraftRevision'>) => void;
  onReplace: (skill: DraftSkillResponse, replacement: TaxonomySkillResponse) => void;
  onDelete: (skill: DraftSkillResponse) => void;
}) {
  const [level, setLevel] = useState<SkillLevel>(skill.level);
  const [weight, setWeight] = useState(String(skill.weight));
  const [note, setNote] = useState(skill.note ?? '');
  const [showReplacement, setShowReplacement] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    setLevel(skill.level);
    setWeight(String(skill.weight));
    setNote(skill.note ?? '');
  }, [skill.level, skill.note, skill.rowVersion, skill.weight]);

  const removed = skill.decision === 'REMOVED';
  const confidence = confidencePercent(skill.matchScore);

  function save(event: React.FormEvent) {
    event.preventDefault();
    const parsedWeight = Number(weight);
    if (!Number.isFinite(parsedWeight) || parsedWeight < 0 || parsedWeight > 1) {
      setFormError('Weight must be a number from 0 to 1.');
      return;
    }
    setFormError(null);
    let decision = skill.decision;
    if (skill.decision === 'PENDING' && skill.canonicalSkillId) decision = 'ACCEPTED';
    onSave(skill, {
      level,
      weight: parsedWeight,
      note: note.trim() || undefined,
      decision,
    });
  }

  return (
    <Card as="li" className={`draft-skill draft-skill--${skill.decision.toLowerCase()}`}>
      <div className="draft-skill__head">
        <div>
          <p className="draft-skill__term">Extracted term</p>
          <h3>{skill.term}</h3>
        </div>
        <span className={`decision-badge decision-badge--${skill.decision.toLowerCase()}`}>
          {decisionLabel(skill.decision)}
        </span>
      </div>

      <div className="canonical-match">
        <div>
          <span className="canonical-match__label">Canonical skill</span>
          <strong>{skill.canonicalSkillLabel ?? 'No canonical match'}</strong>
          {skill.canonicalSkillId && <code>{skill.canonicalSkillId}</code>}
        </div>
        {confidence && <span title="Automated matcher confidence">{confidence} match</span>}
      </div>

      {skill.decision === 'REPLACED' && skill.originalCanonicalSkillLabel && (
        <p className="review-callout">
          Replaced automated suggestion “{skill.originalCanonicalSkillLabel}”.
        </p>
      )}
      {!skill.canonicalSkillId && !removed && (
        <p className="review-callout review-callout--warn">
          This term is unresolved. Choose a canonical replacement before publishing.
        </p>
      )}
      {duplicate && !removed && (
        <p className="review-callout review-callout--warn">
          This canonical skill appears more than once in the active draft. Replace or remove a
          duplicate before publishing.
        </p>
      )}
      {skill.matchReason && <p className="draft-skill__reason">{skill.matchReason}</p>}

      <details className="review-details">
        <summary>
          Evidence and alternatives ({skill.evidenceCount || skill.evidence.length})
        </summary>
        <div className="review-details__body">
          {skill.sources.length > 0 && (
            <p>
              <strong>Sources:</strong> {skill.sources.join(', ')}
            </p>
          )}
          {skill.evidence.length > 0 ? (
            <ul>
              {skill.evidence.slice(0, 6).map((item, index) => (
                <li key={index}>{evidenceText(item)}</li>
              ))}
            </ul>
          ) : (
            <p className="cell__quiet">No text evidence was returned.</p>
          )}
          {skill.candidates.length > 0 && (
            <div>
              <strong>Other matcher candidates</strong>
              <ul className="candidate-list list-reset">
                {skill.candidates.map((candidate) => (
                  <li key={candidate.skillId}>
                    <span>
                      {candidate.label}{' '}
                      <small>{confidencePercent(candidate.score) ?? '—'}</small>
                    </span>
                    {!readOnly && !removed && (
                      <button
                        type="button"
                        className="button button--quiet button--small button--auto"
                        disabled={busy || unavailableReplacementIds.has(candidate.skillId)}
                        onClick={() =>
                          onReplace(skill, {
                            skillId: candidate.skillId,
                            label: candidate.label,
                          })
                        }
                      >
                        {unavailableReplacementIds.has(candidate.skillId)
                          ? 'Already used'
                          : 'Use this skill'}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>

      {!readOnly && !removed && (
        <form className="draft-skill__form" onSubmit={save}>
          <div className="form__row">
            <Select
              label="Level"
              options={LEVEL_OPTIONS}
              value={level}
              onChange={(event) => setLevel(event.target.value as SkillLevel)}
              disabled={busy}
            />
            <TextField
              label="Weight"
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={weight}
              onChange={(event) => {
                setWeight(event.target.value);
                setFormError(null);
              }}
              hint="0 to 1"
              error={formError ?? undefined}
              disabled={busy}
            />
          </div>
          <TextArea
            label="Reviewer note"
            optional
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why you accepted or changed this skill"
            disabled={busy}
          />
          <div className="draft-skill__actions">
            <button
              type="submit"
              className="button button--primary button--small button--auto"
              disabled={busy}
            >
              {busy
                ? 'Saving…'
                : skill.decision === 'PENDING' && skill.canonicalSkillId
                  ? 'Save and accept'
                  : 'Save changes'}
            </button>
            <button
              type="button"
              className="button button--secondary button--small button--auto"
              onClick={() => setShowReplacement((shown) => !shown)}
              aria-expanded={showReplacement}
              disabled={busy}
            >
              {showReplacement ? 'Close replacement search' : 'Replace skill'}
            </button>
            <button
              type="button"
              className="button button--quiet button--small button--auto draft-skill__remove"
              onClick={() => onDelete(skill)}
              disabled={busy}
            >
              Remove
            </button>
          </div>
        </form>
      )}

      {!readOnly && !removed && showReplacement && (
        <div className="replacement-panel">
          <h4>Choose a canonical replacement</h4>
          <p>Replacing keeps the extracted term and audit history, but changes its canonical ID.</p>
          <TaxonomyPicker
            token={token}
            disabled={busy}
            disabledSkillIds={unavailableReplacementIds}
            onChoose={(replacement) => onReplace(skill, replacement)}
          />
        </div>
      )}
    </Card>
  );
}

function AddSkillPanel({
  token,
  busy,
  unavailableSkillIds,
  onAdd,
}: {
  token: string;
  busy: boolean;
  unavailableSkillIds: Set<string>;
  onAdd: (input: {
    skill: TaxonomySkillResponse;
    term?: string;
    level: SkillLevel;
    weight: number;
    note?: string;
  }) => void;
}) {
  const [selected, setSelected] = useState<TaxonomySkillResponse | null>(null);
  const [term, setTerm] = useState('');
  const [level, setLevel] = useState<SkillLevel>('beginner');
  const [weight, setWeight] = useState('0.5');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const parsedWeight = Number(weight);
    if (!selected) {
      setError('Search for and choose a canonical skill first.');
      return;
    }
    if (!Number.isFinite(parsedWeight) || parsedWeight < 0 || parsedWeight > 1) {
      setError('Weight must be a number from 0 to 1.');
      return;
    }
    setError(null);
    onAdd({
      skill: selected,
      term: term.trim() || undefined,
      level,
      weight: parsedWeight,
      note: note.trim() || undefined,
    });
  }

  return (
    <Card className="add-skill">
      <h2 className="section__title">Add a missing skill</h2>
      <p className="section__lede">
        Add from the canonical taxonomy so the published course map cannot create duplicate
        free-text skill identities.
      </p>
      <TaxonomyPicker
        token={token}
        disabled={busy}
        disabledSkillIds={unavailableSkillIds}
        onChoose={(skill) => {
          setSelected(skill);
          setError(null);
        }}
      />
      {selected && (
        <div className="selected-taxonomy" role="status">
          <span>
            Selected: <strong>{selected.label}</strong>
          </span>
          <button
            type="button"
            className="button button--quiet button--small button--auto"
            onClick={() => setSelected(null)}
            disabled={busy}
          >
            Clear
          </button>
        </div>
      )}
      <form className="form" onSubmit={submit}>
        <TextField
          label="Term found in the course"
          optional
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder={selected?.label ?? 'Defaults to the canonical label'}
          disabled={busy}
        />
        <div className="form__row">
          <Select
            label="Level"
            options={LEVEL_OPTIONS}
            value={level}
            onChange={(event) => setLevel(event.target.value as SkillLevel)}
            disabled={busy}
          />
          <TextField
            label="Weight"
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={weight}
            onChange={(event) => {
              setWeight(event.target.value);
              setError(null);
            }}
            hint="0 to 1"
            disabled={busy}
          />
        </div>
        <TextArea
          label="Reviewer note"
          optional
          rows={2}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          disabled={busy}
        />
        {error && (
          <p className="field__error" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          className="button button--primary button--auto"
          disabled={busy || !selected}
        >
          {busy ? 'Adding…' : 'Add skill to draft'}
        </button>
      </form>
    </Card>
  );
}

/** Review and publish the AI-generated course-skill proposal. */
export function LearningOutcomeReviewPage() {
  const { session } = useAuth();
  const token = session!.token;
  const routeId = useParams().outcomeId;
  const outcomeId = Number(routeId);
  const validOutcomeId = Number.isInteger(outcomeId) && outcomeId > 0;

  const outcome = useAsync(
    () =>
      validOutcomeId
        ? contentManagerApi.getLearningOutcome(token, outcomeId)
        : Promise.reject(new Error('This learning-outcome link is invalid.')),
    [token, outcomeId, validOutcomeId],
  );
  const canLoadSkills =
    outcome.data !== undefined &&
    ['READY_FOR_REVIEW', 'PUBLISHING', 'PUBLISHED'].includes(outcome.data.extractionStatus);
  const skills = useAsync(
    () =>
      canLoadSkills
        ? contentManagerApi.listDraftSkills(token, outcomeId)
        : Promise.resolve<DraftSkillResponse[]>([]),
    [token, outcomeId, canLoadSkills],
  );

  const [filter, setFilter] = useState<Filter>('ALL');
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<DraftSkillResponse | null>(null);
  const [replacing, setReplacing] = useState<{
    skill: DraftSkillResponse;
    replacement: TaxonomySkillResponse;
  } | null>(null);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);

  const rows = useMemo(() => skills.data ?? [], [skills.data]);

  // Rows are ordered once per load and keep their positions while the reviewer
  // works; re-sorting is an explicit action, never a side effect of editing.
  const [orderIds, setOrderIds] = useState<number[] | null>(null);
  useEffect(() => {
    setOrderIds(null);
  }, [outcomeId]);
  useEffect(() => {
    if (skills.loading || skills.failed) return;
    const next = rows;
    setOrderIds((prev) => {
      if (prev && prev.length > 0 && next.length > 0) return mergeReviewOrder(prev, next);
      return sortDraftSkillsForReview(next).map((skill) => skill.draftSkillId);
    });
  }, [skills.loading, skills.failed, rows]);

  const orderedRows = useMemo(() => {
    if (!orderIds || orderIds.length === 0) return rows;
    const byId = new Map(rows.map((row) => [row.draftSkillId, row] as const));
    const placed = orderIds.flatMap((id) => {
      const row = byId.get(id);
      byId.delete(id);
      return row ? [row] : [];
    });
    // Rows that raced past the merge (should not happen) still render.
    return placed.length === rows.length ? placed : [...placed, ...byId.values()];
  }, [rows, orderIds]);

  const queueCounts = useMemo(() => {
    const counts: Record<ReturnType<typeof reviewPriority>, number> = {
      blocked: 0,
      judgment: 0,
      quick: 0,
      archived: 0,
    };
    for (const row of rows) counts[reviewPriority(row)] += 1;
    return counts;
  }, [rows]);

  const active = activeDraftSkills(rows);
  const duplicateIds = duplicateCanonicalIds(rows);
  const pendingCount = active.filter((skill) => skill.decision === 'PENDING').length;
  const unresolvedCount = active.filter((skill) => !skill.canonicalSkillId).length;
  const approvedCount = active.filter((skill) => skill.decision !== 'PENDING').length;
  const readOnly = outcome.data?.extractionStatus !== 'READY_FOR_REVIEW';

  const filteredRows = useMemo(
    () => (filter === 'ALL' ? orderedRows : orderedRows.filter((skill) => skill.decision === filter)),
    [filter, orderedRows],
  );
  const activeCanonicalIds = useMemo(
    () =>
      new Set(
        active
          .map((skill) => skill.canonicalSkillId)
          .filter((id): id is string => id !== undefined),
      ),
    [active],
  );

  const polling = outcome.data !== undefined && isRunningStatus(outcome.data.extractionStatus);
  useEffect(() => {
    if (!polling || !validOutcomeId) return;
    let live = true;
    async function poll() {
      try {
        const updated = await contentManagerApi.getExtractionStatus(token, outcomeId);
        if (!live) return;
        outcome.setData(updated);
        setPollError(null);
      } catch (cause) {
        if (live) setPollError(messageFor(cause));
      }
    }
    void poll();
    const timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
    // The status transition tears down polling and lets the skills loader start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outcome.data?.extractionStatus, outcomeId, polling, token, validOutcomeId]);

  async function refreshReview() {
    const [nextOutcome, nextSkills] = await Promise.all([
      contentManagerApi.getLearningOutcome(token, outcomeId),
      contentManagerApi.listDraftSkills(token, outcomeId),
    ]);
    outcome.setData(nextOutcome);
    skills.setData(nextSkills);
  }

  async function mutate(key: string, successMessage: string, operation: () => Promise<unknown>) {
    setBusyKey(key);
    setActionError(null);
    setSuccess(null);
    try {
      await operation();
      await refreshReview();
      setSuccess(successMessage);
      return true;
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        try {
          await refreshReview();
          setActionError(
            new Error(`${cause.message} The latest draft has been loaded; review it and try again.`),
          );
        } catch {
          setActionError(cause);
        }
      } else {
        setActionError(cause);
      }
      return false;
    } finally {
      setBusyKey(null);
    }
  }

  function saveSkill(
    skill: DraftSkillResponse,
    changes: Omit<UpdateDraftSkillRequest, 'expectedRowVersion' | 'expectedDraftRevision'>,
  ) {
    const currentOutcome = outcome.data;
    if (!currentOutcome) return;
    void mutate(
      `save:${skill.draftSkillId}`,
      `“${skill.term}” was saved${skill.decision === 'PENDING' && skill.canonicalSkillId ? ' and accepted' : ''}.`,
      () =>
        contentManagerApi.updateDraftSkill(token, outcomeId, skill.draftSkillId, {
          ...changes,
          expectedRowVersion: skill.rowVersion,
          expectedDraftRevision: currentOutcome.draftRevision,
        }),
    );
  }

  async function confirmReplacement() {
    if (!replacing || !outcome.data) return;
    const { skill, replacement } = replacing;
    const changed = await mutate(
      `replace:${skill.draftSkillId}`,
      `“${skill.term}” was replaced with “${replacement.label}”.`,
      () =>
        contentManagerApi.replaceDraftSkill(token, outcomeId, skill.draftSkillId, {
          replacementSkillId: replacement.skillId,
          note: skill.note,
          expectedRowVersion: skill.rowVersion,
          expectedDraftRevision: outcome.data!.draftRevision,
        }),
    );
    if (changed) setReplacing(null);
  }

  async function confirmDelete() {
    if (!deleting || !outcome.data) return;
    const changed = await mutate(
      `delete:${deleting.draftSkillId}`,
      `“${deleting.term}” was removed from the draft.`,
      () =>
        contentManagerApi.deleteDraftSkill(token, outcomeId, deleting.draftSkillId, {
          expectedRowVersion: deleting.rowVersion,
          expectedDraftRevision: outcome.data!.draftRevision,
        }),
    );
    if (changed) setDeleting(null);
  }

  function addSkill(input: {
    skill: TaxonomySkillResponse;
    term?: string;
    level: SkillLevel;
    weight: number;
    note?: string;
  }) {
    if (!outcome.data) return;
    void mutate('add', `“${input.skill.label}” was added to the draft.`, () =>
      contentManagerApi.addDraftSkill(token, outcomeId, {
        skillId: input.skill.skillId,
        skillLabel: input.skill.label,
        term: input.term,
        level: input.level,
        weight: input.weight,
        note: input.note,
        expectedDraftRevision: outcome.data!.draftRevision,
      }),
    );
  }

  async function publish() {
    if (!outcome.data) return;
    setBusyKey('publish');
    setActionError(null);
    setSuccess(null);
    try {
      const updated = await contentManagerApi.publishLearningOutcome(token, outcomeId, {
        expectedDraftRevision: outcome.data.draftRevision,
      });
      outcome.setData(updated);
      setSuccess(
        updated.extractionStatus === 'PUBLISHED'
          ? 'The reviewed course-skill map is now published.'
          : 'Publication started. This page will update when the course map is live.',
      );
      setConfirmPublish(false);
    } catch (cause) {
      setActionError(cause);
    } finally {
      setBusyKey(null);
    }
  }

  async function retryExtraction() {
    setBusyKey('retry');
    setActionError(null);
    try {
      const updated = await contentManagerApi.retryExtraction(token, outcomeId);
      outcome.setData(updated);
      setSuccess('Skill extraction was restarted.');
    } catch (cause) {
      setActionError(cause);
    } finally {
      setBusyKey(null);
    }
  }

  async function cancelExtraction() {
    setBusyKey('cancel');
    setActionError(null);
    try {
      const updated = await contentManagerApi.cancelExtraction(token, outcomeId);
      outcome.setData(updated);
      setSuccess('Skill extraction was cancelled.');
      setConfirmCancel(false);
    } catch (cause) {
      setActionError(cause);
    } finally {
      setBusyKey(null);
    }
  }

  const publishBlockers: string[] = [];
  if (active.length === 0) publishBlockers.push('Keep at least one skill in the course map.');
  if (pendingCount > 0) {
    publishBlockers.push(`Resolve ${pendingCount} pending skill${pendingCount === 1 ? '' : 's'}.`);
  }
  if (unresolvedCount > 0) {
    publishBlockers.push(
      `Replace ${unresolvedCount} unresolved term${unresolvedCount === 1 ? '' : 's'} with canonical skills.`,
    );
  }
  if (duplicateIds.size > 0) {
    publishBlockers.push(
      `Remove or replace ${duplicateIds.size} duplicated canonical skill${duplicateIds.size === 1 ? '' : 's'}.`,
    );
  }

  if (!validOutcomeId) {
    return (
      <AppShell>
        <ErrorState message="This learning-outcome link is invalid." />
      </AppShell>
    );
  }

  return (
    <AppShell careerPath={outcome.data?.studyFieldName}>
      <PageHeader
        title={outcome.data ? `Review ${outcome.data.courseCode}` : 'Review extracted skills'}
        lede={
          outcome.data
            ? `${outcome.data.courseName} · ${outcome.data.catalogVersion}`
            : 'Review the extracted course-skill proposal before publication.'
        }
        action={
          <Link className="button button--secondary button--small button--auto" to="/content">
            Back to uploads
          </Link>
        }
      />

      {success && (
        <div className="notice notice--ok" role="status">
          {success}
        </div>
      )}
      {actionError != null && <Banner message={messageFor(actionError)} />}
      {pollError && <Banner message={`Live status updates failed: ${pollError}`} />}

      {outcome.loading && <Skeleton rows={4} />}
      {!outcome.loading && outcome.failed && (
        <ErrorState message={messageFor(outcome.error)} onRetry={outcome.reload} />
      )}

      {!outcome.loading && outcome.data && (
        <div className="stack">
          <Card className="review-summary">
            <div className="review-summary__head">
              <div>
                <div className="outcome__identity">
                  <span>{outcome.data.institutionCode}</span>
                  <span>{outcome.data.courseCode}</span>
                  <span>{outcome.data.catalogVersion}</span>
                </div>
                <p className="cell__quiet">
                  Uploaded {formatDate(outcome.data.uploadedAt)}
                  {outcome.data.taxonomyVersion
                    ? ` · Taxonomy ${outcome.data.taxonomyVersion}`
                    : ''}
                </p>
              </div>
              <span
                className={`workflow-badge workflow-badge--${statusTone(outcome.data.extractionStatus)}`}
              >
                {polling && <span className="workflow-badge__dot" aria-hidden="true" />}
                {statusLabel(outcome.data.extractionStatus)}
              </span>
            </div>
            {outcome.data.warnings.length > 0 && (
              <details className="review-details">
                <summary>{outcome.data.warnings.length} extraction warning(s)</summary>
                <ul>
                  {outcome.data.warnings.map((warning, index) => (
                    <li key={`${warning}-${index}`}>{warning}</li>
                  ))}
                </ul>
              </details>
            )}
          </Card>

          {['UPLOADED', 'QUEUED', 'EXTRACTING', 'PUBLISHING'].includes(
            outcome.data.extractionStatus,
          ) && (
            <Card>
              <div className="working" aria-live="polite">
                <span className="spinner" aria-hidden="true" />
                <div>
                  <strong>
                    {outcome.data.extractionStatus === 'PUBLISHING'
                      ? 'Publishing the reviewed course map…'
                      : 'Extracting skills from the PDF…'}
                  </strong>
                  <p>
                    You can leave this page. Processing continues in the background and this
                    status refreshes automatically.
                  </p>
                </div>
              </div>
              {outcome.data.extractionStatus !== 'PUBLISHING' && (
                <button
                  type="button"
                  className="button button--quiet button--small button--auto"
                  onClick={() => setConfirmCancel(true)}
                  disabled={busyKey != null}
                >
                  Cancel extraction
                </button>
              )}
            </Card>
          )}

          {outcome.data.extractionStatus === 'FAILED' && (
            <div className="empty empty--error" role="alert">
              <h2 className="empty__title">Skill extraction failed</h2>
              <p className="empty__body">
                {outcome.data.extractionError ??
                  'The PDF could not be analysed. The draft was not published.'}
              </p>
              <div className="empty__action">
                <button
                  type="button"
                  className="button button--secondary button--auto"
                  onClick={() => void retryExtraction()}
                  disabled={busyKey != null}
                >
                  {busyKey === 'retry' ? 'Restarting…' : 'Retry extraction'}
                </button>
              </div>
            </div>
          )}

          {outcome.data.extractionStatus === 'CANCELLED' && (
            <EmptyState
              title="Extraction was cancelled"
              body="The PDF is still stored. Restart extraction when you are ready to review it."
              action={
                <button
                  type="button"
                  className="button button--primary button--auto"
                  onClick={() => void retryExtraction()}
                  disabled={busyKey != null}
                >
                  {busyKey === 'retry' ? 'Restarting…' : 'Retry extraction'}
                </button>
              }
            />
          )}

          {canLoadSkills && (
            <>
              {outcome.data.extractionStatus === 'PUBLISHED' && (
                <div className="notice notice--ok" role="status">
                  This is the published course map
                  {outcome.data.courseMapVersion === undefined
                    ? '.'
                    : ` (version ${outcome.data.courseMapVersion}).`}{' '}
                  Upload a new catalog version to propose changes without affecting this one.
                </div>
              )}

              <div className="grid grid--stats review-stats">
                <Stat label="Extracted" value={rows.length} />
                <Stat label="Approved" value={approvedCount} />
                <Stat label="Pending" value={pendingCount} />
                <Stat label="Unresolved" value={unresolvedCount} />
              </div>

              <section className="stack" aria-labelledby="skills-title">
                <div className="section-heading section-heading--wrap">
                  <div>
                    <h2 className="section__title" id="skills-title">
                      Course skills <span className="section__count">{rows.length}</span>
                    </h2>
                    <p className="section__lede">
                      Review the canonical match, evidence, level, and weight for every term. Rows
                      hold their position while you work; re-sorting is manual.
                    </p>
                  </div>
                  <div className="section-heading__actions">
                    <button
                      type="button"
                      className="button button--secondary button--small button--auto"
                      onClick={() =>
                        setOrderIds(sortDraftSkillsForReview(rows).map((skill) => skill.draftSkillId))
                      }
                      disabled={busyKey != null || skills.loading || rows.length === 0}
                      title="Unresolved blockers first, then lowest-margin judgment calls, then high-confidence accepts"
                    >
                      Re-sort by priority
                    </button>
                    <button
                      type="button"
                      className="button button--secondary button--small button--auto"
                      onClick={() => void refreshReview().catch(setActionError)}
                      disabled={busyKey != null || skills.loading}
                    >
                      Refresh draft
                    </button>
                  </div>
                </div>

                {rows.length > 0 && (
                  <p className="cell__quiet" role="status">
                    Priority order: {queueCounts.blocked} blocking publish ·{' '}
                    {queueCounts.judgment} needing judgment · {queueCounts.quick} quick accepts.
                    Duplicate canonical skills are placed next to each other.
                  </p>
                )}

                <div className="review-filters" role="group" aria-label="Filter skills by decision">
                  {FILTERS.map((item) => {
                    const count =
                      item.value === 'ALL'
                        ? rows.length
                        : rows.filter((skill) => skill.decision === item.value).length;
                    return (
                      <button
                        type="button"
                        key={item.value}
                        className={`review-filter${filter === item.value ? ' review-filter--active' : ''}`}
                        aria-pressed={filter === item.value}
                        onClick={() => setFilter(item.value)}
                      >
                        {item.label} <span>{count}</span>
                      </button>
                    );
                  })}
                </div>

                {skills.loading && <Skeleton rows={4} />}
                {!skills.loading && skills.failed && (
                  <ErrorState message={messageFor(skills.error)} onRetry={skills.reload} />
                )}
                {!skills.loading && !skills.failed && filteredRows.length === 0 && (
                  <EmptyState
                    title={rows.length === 0 ? 'No skills were extracted' : 'No skills in this filter'}
                    body={
                      rows.length === 0
                        ? 'Add the canonical skills this course teaches before publishing.'
                        : 'Choose another filter to continue reviewing the draft.'
                    }
                  />
                )}
                {!skills.loading && !skills.failed && filteredRows.length > 0 && (
                  <ul className="draft-skills list-reset">
                    {filteredRows.map((skill) => {
                      const unavailableReplacementIds = new Set(activeCanonicalIds);
                      if (skill.canonicalSkillId) {
                        unavailableReplacementIds.delete(skill.canonicalSkillId);
                      }
                      return (
                        <SkillDraftCard
                          key={skill.draftSkillId}
                          skill={skill}
                          token={token}
                          duplicate={
                            skill.canonicalSkillId !== undefined &&
                            duplicateIds.has(skill.canonicalSkillId)
                          }
                          readOnly={readOnly}
                          busy={
                            busyKey != null &&
                            (busyKey.endsWith(`:${skill.draftSkillId}`) || busyKey === 'publish')
                          }
                          unavailableReplacementIds={unavailableReplacementIds}
                          onSave={saveSkill}
                          onReplace={(draft, replacement) => setReplacing({ skill: draft, replacement })}
                          onDelete={setDeleting}
                        />
                      );
                    })}
                  </ul>
                )}
              </section>

              {!readOnly && (
                <AddSkillPanel
                  token={token}
                  busy={busyKey != null}
                  unavailableSkillIds={activeCanonicalIds}
                  onAdd={addSkill}
                />
              )}

              {!readOnly && (
                <Card className="publish-panel">
                  <div>
                    <h2 className="section__title">Approve and publish</h2>
                    <p className="section__lede">
                      Publication replaces this course version atomically. Students never see the
                      unreviewed draft.
                    </p>
                    {publishBlockers.length > 0 ? (
                      <ul className="publish-blockers">
                        {publishBlockers.map((blocker) => (
                          <li key={blocker}>{blocker}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="review-callout review-callout--ok">
                        All active skills are resolved and reviewed. This draft is ready to publish.
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    className="button button--primary button--auto"
                    onClick={() => setConfirmPublish(true)}
                    disabled={publishBlockers.length > 0 || busyKey != null}
                    aria-describedby={publishBlockers.length > 0 ? 'publish-disabled-reason' : undefined}
                  >
                    {busyKey === 'publish' ? 'Publishing…' : 'Approve and publish'}
                  </button>
                  {publishBlockers.length > 0 && (
                    <span className="visually-hidden" id="publish-disabled-reason">
                      Resolve the listed review blockers before publishing.
                    </span>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title="Remove this skill from the draft?"
          body={`“${deleting.term}” will be marked as removed and excluded from publication. Its review history is retained.`}
          confirmLabel="Remove skill"
          destructive
          busy={busyKey === `delete:${deleting.draftSkillId}`}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setDeleting(null)}
        />
      )}

      {replacing && (
        <ConfirmDialog
          title="Replace the canonical skill?"
          body={`“${replacing.skill.term}” will use “${replacing.replacement.label}” instead of “${replacing.skill.canonicalSkillLabel ?? 'the unresolved suggestion'}”.`}
          confirmLabel="Replace skill"
          busy={busyKey === `replace:${replacing.skill.draftSkillId}`}
          onConfirm={() => void confirmReplacement()}
          onCancel={() => setReplacing(null)}
        />
      )}

      {confirmPublish && (
        <ConfirmDialog
          title="Publish this reviewed course map?"
          body={`${active.length} approved skill${active.length === 1 ? '' : 's'} will become available to student analysis for ${outcome.data?.courseCode ?? 'this course'} (${outcome.data?.catalogVersion ?? 'this catalog version'}).`}
          confirmLabel="Publish course map"
          busy={busyKey === 'publish'}
          onConfirm={() => void publish()}
          onCancel={() => setConfirmPublish(false)}
        />
      )}

      {confirmCancel && (
        <ConfirmDialog
          title="Cancel skill extraction?"
          body="Processing will stop, but the uploaded PDF will remain available for a later retry."
          confirmLabel="Cancel extraction"
          busy={busyKey === 'cancel'}
          onConfirm={() => void cancelExtraction()}
          onCancel={() => setConfirmCancel(false)}
        />
      )}
    </AppShell>
  );
}

