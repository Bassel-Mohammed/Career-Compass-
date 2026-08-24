import { useState } from 'react';
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
import { messageFor, prerequisiteFor, storageMessageFor } from '../../api/errors';
import type { LearningOutcomeResponse } from '../../types';

/** `course_name` is VARCHAR(200) and has no server-side validation — see below. */
const MAX_COURSE_NAME = 200;

/**
 * FR-CM-04 — upload course learning-outcome PDFs, and manage what has been uploaded.
 *
 * Two things shape this screen more than anything else.
 *
 * **Nothing processes the file.** It is written to disk and recorded in the database, and that
 * is the end of the path — `LearningOutcomeService` has no AI client and the response carries
 * no status field. So the screen says the document is stored, and does not imply extraction,
 * progress or a skill mapping that does not exist.
 *
 * **The server-side validation is thin.** `courseName` has no `@NotBlank` and no length check,
 * a missing part has no exception handler, and an oversized file is killed by Spring's
 * multipart limit before the service's friendly message can run — all three surface as a 500.
 * The client-side checks here are what stands between the user and "Something went wrong on
 * our end."
 */
export function LearningOutcomesPage() {
  const { session } = useAuth();
  const token = session!.token;

  const profile = useAsync(() => contentManagerApi.getProfile(token), [token]);
  const outcomes = useAsync(() => contentManagerApi.listLearningOutcomes(token), [token]);
  const upload = useAction(contentManagerApi.uploadLearningOutcome);
  const removeFile = useAction(contentManagerApi.deleteOutcomeFile);

  const [courseName, setCourseName] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<LearningOutcomeResponse | null>(null);

  // Checked here as well as by the upload's own error, so the form is disabled up front
  // rather than letting someone fill it in and only then be turned away.
  const missingStudyField = profile.data !== undefined && profile.data.studyFieldId === undefined;
  const uploadPrereq = prerequisiteFor(upload.error, 'CONTENT_MANAGER');

  const rows = outcomes.data ?? [];
  const duplicate = rows.some(
    (r) => r.courseName.trim().toLowerCase() === courseName.trim().toLowerCase(),
  );

  function validateName(): boolean {
    const trimmed = courseName.trim();
    if (!trimmed) {
      setNameError('A course name is required');
      return false;
    }
    if (trimmed.length > MAX_COURSE_NAME) {
      setNameError(`Course name must be ${MAX_COURSE_NAME} characters or fewer`);
      return false;
    }
    setNameError(null);
    return true;
  }

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!validateName() || !file) return;

    const created = await upload.run(token, {
      courseName: courseName.trim(),
      description: description.trim() || undefined,
      file,
    });
    if (created) {
      outcomes.setData([created, ...rows]);
      setCourseName('');
      setDescription('');
      setFile(null);
    }
  }

  async function handleRemove() {
    if (!removing) return;
    const updated = await removeFile.run(token, removing.outcomeId);
    if (updated) {
      outcomes.setData(rows.map((r) => (r.outcomeId === updated.outcomeId ? updated : r)));
      setRemoving(null);
    }
  }

  return (
    <AppShell careerPath={profile.data?.studyFieldName}>
      <PageHeader
        title="Learning outcomes"
        lede="Upload the learning-outcome document for a course you teach. These build the course-to-skill knowledge base the student analysis draws on."
      />

      {profile.loading && <Skeleton rows={2} />}

      {missingStudyField && (
        <PrerequisiteState
          to="/content/profile"
          message="Choose the study field you teach first — uploads are filed under your university and field."
        />
      )}

      {!profile.loading && !missingStudyField && (
        <div className="stack">
          <Card>
            <h2 className="section__title">Upload a document</h2>

            {uploadPrereq && (
              <PrerequisiteState to={uploadPrereq.to} message={uploadPrereq.message} />
            )}
            {upload.failed && !uploadPrereq && <Banner message={storageMessageFor(upload.error)} />}

            <form className="form" onSubmit={handleUpload}>
              <TextField
                label="Course name"
                value={courseName}
                onChange={(e) => {
                  setCourseName(e.target.value);
                  if (nameError) setNameError(null);
                }}
                onBlur={validateName}
                error={nameError ?? undefined}
                placeholder="Data Structures"
                maxLength={MAX_COURSE_NAME}
                disabled={upload.running}
                required
              />

              {/* Nothing server-side prevents this — no unique constraint, no 409 — so an
                  accidental second upload silently creates a second row and a second file.
                  A warning is the only place this can be caught. */}
              {duplicate && (
                <p className="notice notice--preview">
                  You have already uploaded a document for a course with this name. Uploading
                  again adds a second copy rather than replacing the first.
                </p>
              )}

              <TextArea
                label="Description"
                optional
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What the course covers, or which version of the syllabus this is."
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
                    onClick={() => setFile(null)}
                    disabled={upload.running}
                  >
                    Choose another
                  </button>
                </div>
              ) : (
                <FileDrop
                  maxBytes={contentManagerApi.MAX_OUTCOME_BYTES}
                  onSelect={setFile}
                  disabled={upload.running}
                  label="Drop the learning-outcome PDF here, or browse"
                  hint="Text-based PDF, up to 10MB."
                />
              )}

              <div className="actions">
                <button
                  type="submit"
                  className="button button--primary button--auto"
                  disabled={upload.running || !file || !courseName.trim()}
                >
                  {upload.running ? 'Uploading…' : 'Upload document'}
                </button>
                <span className="actions__hint">
                  The document is stored for the knowledge base. It is not analysed yet.
                </span>
              </div>
            </form>
          </Card>

          <section>
            <h2 className="section__title">
              Your uploads
              {!outcomes.loading && <span className="section__count">{rows.length}</span>}
            </h2>

            {outcomes.loading && <Skeleton rows={3} />}
            {!outcomes.loading && outcomes.failed && (
              <ErrorState message={messageFor(outcomes.error)} onRetry={outcomes.reload} />
            )}

            {!outcomes.loading && !outcomes.failed && rows.length === 0 && (
              <EmptyState
                title="Nothing uploaded yet"
                body="Documents you upload appear here, with the course they belong to and whether the original file is still stored."
              />
            )}

            {!outcomes.loading && !outcomes.failed && rows.length > 0 && (
              <>
                {removeFile.failed && <Banner message={storageMessageFor(removeFile.error)} />}
                <ul className="stack list-reset">
                  {rows.map((row) => (
                    <Card as="li" key={row.outcomeId} className="outcome">
                      <div className="outcome__head">
                        <div>
                          <h3 className="outcome__name">{row.courseName}</h3>
                          <p className="cell__quiet">
                            {row.studyFieldName ?? 'Field unknown'} ·{' '}
                            {formatDate(row.uploadedAt)}
                          </p>
                        </div>
                        {/* Means "the raw file was removed", NOT "it was processed" —
                            there is no processing state to report. */}
                        {row.deletedFromDisk ? (
                          <span className="badge badge--unknown">File removed</span>
                        ) : (
                          <span className="badge badge--strong">File stored</span>
                        )}
                      </div>

                      {row.description && <p className="outcome__desc">{row.description}</p>}

                      <div className="outcome__foot">
                        <span className="cell__quiet">
                          {row.deletedFromDisk
                            ? 'The original document is no longer kept.'
                            : row.originalFilename ?? 'Document stored'}
                        </span>
                        {!row.deletedFromDisk && (
                          <button
                            type="button"
                            className="button button--secondary button--small button--auto"
                            onClick={() => setRemoving(row)}
                          >
                            Remove stored file
                          </button>
                        )}
                      </div>
                    </Card>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>
      )}

      {removing && (
        <ConfirmDialog
          title="Remove the stored file?"
          body={`The PDF for "${removing.courseName}" is deleted from the server. The record of the upload is kept, but the document cannot be downloaded or restored afterwards.`}
          confirmLabel="Remove file"
          destructive
          busy={removeFile.running}
          onConfirm={() => void handleRemove()}
          onCancel={() => setRemoving(null)}
        />
      )}
    </AppShell>
  );
}
