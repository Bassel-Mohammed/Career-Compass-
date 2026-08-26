import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { FileDrop } from '../../components/FileDrop';
import { TextArea } from '../../components/TextArea';
import { TextField } from '../../components/TextField';
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
import * as contentManagerApi from '../../api/contentManager';
import { formatDate } from '../../api/format';
import {
  fieldErrorsFor,
  messageFor,
  prerequisiteFor,
  storageMessageFor,
} from '../../api/errors';
import type { LearningOutcomeResponse } from '../../types';
import { isRunningStatus, statusLabel, statusTone } from './workflow';

const MAX_COURSE_CODE = 64;
const MAX_CATALOG_VERSION = 64;
const MAX_COURSE_NAME = 200;
const POLL_INTERVAL_MS = 3_000;

interface UploadErrors {
  courseCode?: string;
  catalogVersion?: string;
  courseName?: string;
  file?: string;
}

function statusDescription(row: LearningOutcomeResponse): string {
  switch (row.extractionStatus) {
    case 'UPLOADED':
      return 'The PDF is stored and will be queued for extraction.';
    case 'QUEUED':
      return 'Waiting for the skill extraction worker.';
    case 'EXTRACTING':
      return 'The PDF is being analysed. This page refreshes automatically.';
    case 'READY_FOR_REVIEW':
      return `${row.totalSkills} extracted skill${row.totalSkills === 1 ? '' : 's'} · ${row.pendingSkills} still pending`;
    case 'PUBLISHING':
      return 'The approved course map is being published.';
    case 'PUBLISHED':
      return row.courseMapVersion === undefined
        ? 'The course map is available to student analysis.'
        : `Course map ${row.courseMapVersion} is available to student analysis.`;
    case 'FAILED':
      return row.extractionError ?? 'The PDF could not be analysed. You can retry safely.';
    case 'CANCELLED':
      return 'Extraction was cancelled. The PDF remains available for a retry.';
  }
}

/** Upload syllabi, monitor extraction, and enter the review workspace. */
export function LearningOutcomesPage() {
  const { session } = useAuth();
  const token = session!.token;

  const profile = useAsync(() => contentManagerApi.getProfile(token), [token]);
  const outcomes = useAsync(() => contentManagerApi.listLearningOutcomes(token), [token]);
  const upload = useAction(contentManagerApi.uploadLearningOutcome);
  const removeFile = useAction(contentManagerApi.deleteOutcomeFile);

  const [courseCode, setCourseCode] = useState('');
  const [catalogVersion, setCatalogVersion] = useState('');
  const [courseName, setCourseName] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<UploadErrors>({});
  const [previewing, setPreviewing] = useState(false);
  const [previewNote, setPreviewNote] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [rowError, setRowError] = useState<unknown>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [rowAction, setRowAction] = useState<string | null>(null);
  const [removing, setRemoving] = useState<LearningOutcomeResponse | null>(null);
  const [cancelling, setCancelling] = useState<LearningOutcomeResponse | null>(null);

  const missingStudyField = profile.data !== undefined && profile.data.studyFieldId === undefined;
  const uploadPrereq = prerequisiteFor(upload.error, 'CONTENT_MANAGER');
  const rows = useMemo(() => outcomes.data ?? [], [outcomes.data]);
  const serverErrors = fieldErrorsFor(upload.error);

  const duplicate = useMemo(
    () =>
      rows.some(
        (row) =>
          row.courseCode.trim().toLowerCase() === courseCode.trim().toLowerCase() &&
          row.catalogVersion.trim().toLowerCase() === catalogVersion.trim().toLowerCase(),
      ),
    [catalogVersion, courseCode, rows],
  );

  // Only active rows are polled, and only their small extraction resource is requested.
  // Completed rows stop the timer automatically.
  const pollKey = rows
    .filter((row) => isRunningStatus(row.extractionStatus))
    .map((row) => `${row.outcomeId}:${row.extractionStatus}`)
    .join(',');

  useEffect(() => {
    const activeRows = rows.filter((row) => isRunningStatus(row.extractionStatus));
    if (activeRows.length === 0) return;

    let live = true;
    async function poll() {
      const settled = await Promise.allSettled(
        activeRows.map((row) => contentManagerApi.getExtractionStatus(token, row.outcomeId)),
      );
      if (!live) return;

      const updates = new Map<number, LearningOutcomeResponse>();
      for (const result of settled) {
        if (result.status === 'fulfilled') updates.set(result.value.outcomeId, result.value);
      }
      if (updates.size > 0) {
        outcomes.setData(rows.map((row) => updates.get(row.outcomeId) ?? row));
        setPollError(null);
      } else {
        setPollError('Live extraction updates are temporarily unavailable. Use Refresh to try again.');
      }
    }

    void poll();
    const timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
    // pollKey intentionally changes only when the set of active workflows changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollKey, token]);

  /**
   * Ask the backend to read the course identity off the dropped PDF and pre-fill
   * the empty form fields. Suggestions only: whatever the content manager already
   * typed is kept, because course code + catalog version are the qualified
   * identity they are accountable for.
   */
  async function autoFillFromPdf(selected: File) {
    setPreviewing(true);
    setPreviewNote(null);
    try {
      const suggestion = await contentManagerApi.previewLearningOutcomePdf(token, selected);
      setCourseCode((current) => current.trim() || suggestion.courseCode?.trim() || '');
      setCourseName((current) => current.trim() || suggestion.courseName?.trim() || '');
      setDescription((current) => current.trim() || suggestion.description?.trim() || '');
      setPreviewNote(
        suggestion.courseCode || suggestion.courseName
          ? 'Course details were read from the PDF — review them before uploading.'
          : 'No course details were detected in this PDF; fill the form manually.',
      );
    } catch {
      setPreviewNote('Could not read course details from this PDF; fill the form manually.');
    } finally {
      setPreviewing(false);
    }
  }

  function validateUpload(): boolean {    const next: UploadErrors = {};
    const code = courseCode.trim();
    const version = catalogVersion.trim();
    const name = courseName.trim();

    if (!code) next.courseCode = 'A course code is required';
    else if (code.length > MAX_COURSE_CODE) {
      next.courseCode = `Course code must be ${MAX_COURSE_CODE} characters or fewer`;
    }
    if (!version) next.catalogVersion = 'A catalog version is required';
    else if (version.length > MAX_CATALOG_VERSION) {
      next.catalogVersion = `Catalog version must be ${MAX_CATALOG_VERSION} characters or fewer`;
    }
    if (!name) next.courseName = 'A course name is required';
    else if (name.length > MAX_COURSE_NAME) {
      next.courseName = `Course name must be ${MAX_COURSE_NAME} characters or fewer`;
    }
    if (!file) next.file = 'Choose the course PDF to upload';

    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    setSuccess(null);
    if (!validateUpload() || !file) return;

    const created = await upload.run(token, {
      courseCode: courseCode.trim(),
      catalogVersion: catalogVersion.trim(),
      courseName: courseName.trim(),
      description: description.trim() || undefined,
      file,
    });
    if (!created) return;

    outcomes.setData([created, ...rows]);
    setCourseCode('');
    setCatalogVersion('');
    setCourseName('');
    setDescription('');
    setFile(null);
    setPreviewNote(null);
    setErrors({});
    setSuccess(`“${created.courseName}” was uploaded. Skill extraction has started.`);
  }

  async function handleRetry(row: LearningOutcomeResponse) {
    setRowAction(`retry:${row.outcomeId}`);
    setRowError(null);
    setSuccess(null);
    try {
      const updated = await contentManagerApi.retryExtraction(token, row.outcomeId);
      outcomes.setData(rows.map((item) => (item.outcomeId === row.outcomeId ? updated : item)));
      setSuccess(`Skill extraction was restarted for “${row.courseName}”.`);
    } catch (cause) {
      setRowError(cause);
    } finally {
      setRowAction(null);
    }
  }

  async function handleCancel() {
    if (!cancelling) return;
    setRowAction(`cancel:${cancelling.outcomeId}`);
    setRowError(null);
    setSuccess(null);
    try {
      const updated = await contentManagerApi.cancelExtraction(token, cancelling.outcomeId);
      outcomes.setData(
        rows.map((item) => (item.outcomeId === cancelling.outcomeId ? updated : item)),
      );
      setSuccess(`Skill extraction was cancelled for “${cancelling.courseName}”.`);
      setCancelling(null);
    } catch (cause) {
      setRowError(cause);
    } finally {
      setRowAction(null);
    }
  }

  async function handleRemove() {
    if (!removing) return;
    const updated = await removeFile.run(token, removing.outcomeId);
    if (updated) {
      outcomes.setData(rows.map((row) => (row.outcomeId === updated.outcomeId ? updated : row)));
      setSuccess(`The stored PDF for “${removing.courseName}” was removed.`);
      setRemoving(null);
    }
  }

  return (
    <AppShell careerPath={profile.data?.studyFieldName}>
      <PageHeader
        title="Learning outcomes"
        lede="Upload a course PDF, let CareerCompass extract its skills, then review every suggestion before publishing it to student analysis."
      />

      {profile.loading && <Skeleton rows={2} />}
      {!profile.loading && profile.failed && (
        <ErrorState message={messageFor(profile.error)} onRetry={profile.reload} />
      )}
      {!profile.failed && missingStudyField && (
        <PrerequisiteState
          to="/content/profile"
          message="Choose the study field you teach first — uploads are filed under your university and field."
        />
      )}

      {!profile.loading && !profile.failed && !missingStudyField && (
        <div className="stack">
          {success && (
            <div className="notice notice--ok" role="status">
              {success}
            </div>
          )}

          <Card>
            <h2 className="section__title">Upload a course PDF</h2>
            <p className="section__lede">
              Course code and catalog version keep this syllabus separate from similarly named
              courses and older revisions.
            </p>

            {uploadPrereq && (
              <PrerequisiteState to={uploadPrereq.to} message={uploadPrereq.message} />
            )}
            {upload.failed && !uploadPrereq && <Banner message={storageMessageFor(upload.error)} />}

            <form className="form" onSubmit={handleUpload} noValidate>
              <div className="form__row">
                <TextField
                  label="Course code"
                  value={courseCode}
                  onChange={(event) => {
                    setCourseCode(event.target.value);
                    setErrors((current) => ({ ...current, courseCode: undefined }));
                  }}
                  error={errors.courseCode ?? serverErrors.courseCode}
                  placeholder="CS-241"
                  maxLength={MAX_COURSE_CODE}
                  disabled={upload.running}
                  required
                />
                <TextField
                  label="Catalog version"
                  value={catalogVersion}
                  onChange={(event) => {
                    setCatalogVersion(event.target.value);
                    setErrors((current) => ({ ...current, catalogVersion: undefined }));
                  }}
                  error={errors.catalogVersion ?? serverErrors.catalogVersion}
                  hint="For example: 2026-2027 or v3"
                  placeholder="2026-2027"
                  maxLength={MAX_CATALOG_VERSION}
                  disabled={upload.running}
                  required
                />
              </div>

              <TextField
                label="Course name"
                value={courseName}
                onChange={(event) => {
                  setCourseName(event.target.value);
                  setErrors((current) => ({ ...current, courseName: undefined }));
                }}
                error={errors.courseName ?? serverErrors.courseName}
                placeholder="Data Structures"
                maxLength={MAX_COURSE_NAME}
                disabled={upload.running}
                required
              />

              {duplicate && (
                <p className="notice notice--preview" role="status">
                  A syllabus for this course code and catalog version already exists. Use a new
                  catalog version for a revised syllabus.
                </p>
              )}

              <TextArea
                label="Description"
                optional
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What the course covers, or notes about this syllabus revision."
                disabled={upload.running}
              />

              {file ? (
                <div className="chosen">
                  <div>
                    <strong>{file.name}</strong>
                    <p className="cell__quiet">{(file.size / 1024).toFixed(0)} KB</p>
                  </div>
                  <button
                    type="button"
                    className="button button--quiet button--small"
                    onClick={() => {
                      setFile(null);
                      setPreviewNote(null);
                    }}
                    disabled={upload.running}
                  >
                    Choose another
                  </button>
                </div>
              ) : (
                <FileDrop
                  maxBytes={contentManagerApi.MAX_OUTCOME_BYTES}
                  onSelect={(selected) => {
                    setFile(selected);
                    setErrors((current) => ({ ...current, file: undefined }));
                    void autoFillFromPdf(selected);
                  }}
                  disabled={upload.running}
                  label="Drop the course PDF here, or browse"
                  hint="Text-based PDF, up to 10MB. Nothing is published before your review."
                />
              )}
              {(previewing || previewNote) && (
                <p className={`cell__quiet${previewing ? ' preview-loading' : ''}`} role="status">
                  {previewing ? 'Reading course details from the PDF…' : previewNote}
                </p>
              )}
              {errors.file && (
                <p className="field__error" role="alert">
                  {errors.file}
                </p>
              )}

              <div className="actions">
                <button
                  type="submit"
                  className="button button--primary button--auto"
                  disabled={
                    upload.running ||
                    !file ||
                    !courseCode.trim() ||
                    !catalogVersion.trim() ||
                    !courseName.trim()
                  }
                >
                  {upload.running ? 'Uploading…' : 'Upload and extract skills'}
                </button>
                <span className="actions__hint">Extraction continues safely in the background.</span>
              </div>
            </form>
          </Card>

          <section className="stack" aria-labelledby="uploads-title">
            <div className="section-heading">
              <div>
                <h2 className="section__title" id="uploads-title">
                  Your course documents
                  {!outcomes.loading && <span className="section__count">{rows.length}</span>}
                </h2>
                <p className="section__lede">Status updates automatically while extraction runs.</p>
              </div>
              <button
                type="button"
                className="button button--secondary button--small button--auto"
                onClick={outcomes.reload}
                disabled={outcomes.loading}
              >
                Refresh
              </button>
            </div>

            {pollError && <Banner message={pollError} />}
            {rowError != null && <Banner message={messageFor(rowError)} />}
            {removeFile.failed && <Banner message={storageMessageFor(removeFile.error)} />}
            {outcomes.loading && <Skeleton rows={3} />}
            {!outcomes.loading && outcomes.failed && (
              <ErrorState message={messageFor(outcomes.error)} onRetry={outcomes.reload} />
            )}
            {!outcomes.loading && !outcomes.failed && rows.length === 0 && (
              <EmptyState
                title="Nothing uploaded yet"
                body="Upload a course PDF above. Its extracted skills will stay in a private draft until you approve and publish them."
              />
            )}

            {!outcomes.loading && !outcomes.failed && rows.length > 0 && (
              <ul className="stack list-reset">
                {rows.map((row) => {
                  const running = isRunningStatus(row.extractionStatus);
                  const canCancel = ['UPLOADED', 'QUEUED', 'EXTRACTING'].includes(
                    row.extractionStatus,
                  );
                  const canRetry = ['FAILED', 'CANCELLED'].includes(row.extractionStatus);
                  const canReview = ['READY_FOR_REVIEW', 'PUBLISHED'].includes(
                    row.extractionStatus,
                  );
                  return (
                    <Card as="li" key={row.outcomeId} className="outcome">
                      <div className="outcome__head">
                        <div>
                          <div className="outcome__identity">
                            <span>{row.courseCode}</span>
                            <span>{row.catalogVersion}</span>
                          </div>
                          <h3 className="outcome__name">{row.courseName}</h3>
                          <p className="cell__quiet">
                            {row.studyFieldName ?? 'Field unknown'} · {formatDate(row.uploadedAt)}
                          </p>
                        </div>
                        <span
                          className={`workflow-badge workflow-badge--${statusTone(row.extractionStatus)}`}
                        >
                          {running && <span className="workflow-badge__dot" aria-hidden="true" />}
                          {statusLabel(row.extractionStatus)}
                        </span>
                      </div>

                      {row.description && <p className="outcome__desc">{row.description}</p>}
                      <p
                        className={`outcome__status-copy${row.extractionStatus === 'FAILED' ? ' outcome__status-copy--error' : ''}`}
                        aria-live={running ? 'polite' : undefined}
                      >
                        {statusDescription(row)}
                      </p>

                      {row.warnings.length > 0 && (
                        <details className="review-details">
                          <summary>{row.warnings.length} extraction warning(s)</summary>
                          <ul>
                            {row.warnings.map((warning, index) => (
                              <li key={`${warning}-${index}`}>{warning}</li>
                            ))}
                          </ul>
                        </details>
                      )}

                      <div className="outcome__foot">
                        <span className="cell__quiet">
                          {row.deletedFromDisk
                            ? 'Original PDF removed'
                            : row.originalFilename ?? 'PDF stored'}
                        </span>
                        <div className="outcome__actions">
                          {canReview && (
                            <Link
                              className="button button--primary button--small button--auto"
                              to={`/content/learning-outcomes/${row.outcomeId}/review`}
                            >
                              {row.extractionStatus === 'PUBLISHED'
                                ? 'View published skills'
                                : 'Review skills'}
                            </Link>
                          )}
                          {canRetry && (
                            <button
                              type="button"
                              className="button button--secondary button--small button--auto"
                              onClick={() => void handleRetry(row)}
                              disabled={rowAction != null}
                            >
                              {rowAction === `retry:${row.outcomeId}` ? 'Restarting…' : 'Retry extraction'}
                            </button>
                          )}
                          {canCancel && (
                            <button
                              type="button"
                              className="button button--quiet button--small button--auto"
                              onClick={() => setCancelling(row)}
                              disabled={rowAction != null}
                            >
                              Cancel extraction
                            </button>
                          )}
                          {!row.deletedFromDisk && !running && (
                            <button
                              type="button"
                              className="button button--quiet button--small button--auto"
                              onClick={() => setRemoving(row)}
                              disabled={removeFile.running}
                            >
                              Remove PDF
                            </button>
                          )}
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}

      {cancelling && (
        <ConfirmDialog
          title="Cancel skill extraction?"
          body={`CareerCompass will stop processing “${cancelling.courseName}”. The uploaded PDF stays stored, so you can retry later.`}
          confirmLabel="Cancel extraction"
          busy={rowAction === `cancel:${cancelling.outcomeId}`}
          onConfirm={() => void handleCancel()}
          onCancel={() => setCancelling(null)}
        />
      )}

      {removing && (
        <ConfirmDialog
          title="Remove the stored PDF?"
          body={`The PDF for “${removing.courseName}” will be deleted from the server. Its course record and reviewed skill map are kept, but the original document cannot be restored.`}
          confirmLabel="Remove PDF"
          destructive
          busy={removeFile.running}
          onConfirm={() => void handleRemove()}
          onCancel={() => setRemoving(null)}
        />
      )}
    </AppShell>
  );
}
