import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { FileDrop } from '../../components/FileDrop';
import { Card, EmptyState, PageHeader, PrerequisiteState, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as transcriptApi from '../../api/transcript';
import * as jobSeekerApi from '../../api/jobSeeker';
import { formatConfidence } from '../../api/format';
import { messageFor, prerequisiteFor } from '../../api/errors';
import type { ExtractedCourseItem } from '../../types';

/** A row being edited. `id` is local only — the API has no row identity here. */
interface Row {
  id: number;
  courseCode: string;
  courseName: string;
  grade: string;
  lowConfidence: boolean;
  confidence?: number;
  warnings: string[];
}

let nextRowId = 1;

function toRows(courses: ExtractedCourseItem[]): Row[] {
  return courses.map((c) => ({
    id: nextRowId++,
    courseCode: c.courseCode ?? '',
    courseName: c.courseName ?? '',
    grade: c.grade ?? '',
    lowConfidence: c.lowConfidence,
    confidence: c.confidence,
    warnings: c.warnings ?? [],
  }));
}

/**
 * FR-JS-10 and FR-JS-11: upload, then confirm.
 *
 * The two steps are deliberately separate in the backend — uploading persists nothing — and
 * this screen is the reason why. Extraction from a PDF is imperfect, the response flags the
 * rows it is unsure about, and the student is the only one who can say what their transcript
 * actually said. Nothing reaches the database until they press confirm.
 */
export function TranscriptPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const token = session!.token;

  const profile = useAsync(() => jobSeekerApi.getProfile(token), [token]);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [lowConfidenceCount, setLowConfidenceCount] = useState(0);

  const upload = useAction(transcriptApi.uploadTranscript);
  const confirm = useAction(transcriptApi.confirmTranscript);

  // A career path must exist before confirming. Checked up front so the student is not
  // asked to correct a whole table and only then told they cannot save it.
  const missingCareerPath = profile.data !== undefined && profile.data.careerPathId === undefined;

  async function handleFile(file: File) {
    const review = await upload.run(token, file);
    if (!review) return;
    setRows(toRows(review.courses));
    setLowConfidenceCount(review.lowConfidenceCount);
  }

  async function handleConfirm() {
    if (!rows) return;
    const usable = rows.filter((r) => r.courseName.trim() && r.grade.trim());
    const dashboard = await confirm.run(token, {
      courses: usable.map((r) => ({
        courseCode: r.courseCode.trim() || undefined,
        courseName: r.courseName.trim(),
        grade: r.grade.trim(),
      })),
    });
    if (dashboard) navigate('/dashboard');
  }

  function patch(id: number, change: Partial<Row>) {
    setRows((current) =>
      current?.map((r) => (r.id === id ? { ...r, ...change } : r)) ?? current,
    );
  }

  const confirmPrereq = prerequisiteFor(confirm.error, 'JOB_SEEKER');
  const incomplete = rows?.filter((r) => !r.courseName.trim() || !r.grade.trim()).length ?? 0;
  const usableCount = (rows?.length ?? 0) - incomplete;

  return (
    <AppShell careerPath={profile.data?.careerPathTitle}>
      <PageHeader
        title="Your transcript"
        lede="Upload the PDF, check what was read from it, then confirm. Nothing is saved until you confirm."
      />

      {profile.loading && <Skeleton rows={2} />}

      {missingCareerPath && !rows && (
        <PrerequisiteState
          to="/setup"
          message="Choose the career path you want to be measured against first — your skills are scored relative to it."
        />
      )}

      {!profile.loading && !missingCareerPath && !rows && (
        <Card>
          {upload.failed && <Banner message={messageFor(upload.error)} />}
          {upload.running ? (
            <div className="working">
              <span className="spinner" aria-hidden="true" />
              <div>
                <strong>Reading your transcript…</strong>
                <p>
                  Extracting course names and grades. This can take up to half a minute for a
                  long transcript.
                </p>
              </div>
            </div>
          ) : (
            <FileDrop
              maxBytes={transcriptApi.MAX_TRANSCRIPT_BYTES}
              onSelect={(file) => void handleFile(file)}
              label="Drop your transcript PDF here, or browse"
              hint="Text-based PDF, up to 10MB. Scanned images cannot be read."
            />
          )}
        </Card>
      )}

      {rows && (
        <>
          {confirm.failed && !confirmPrereq && <Banner message={messageFor(confirm.error)} />}
          {confirmPrereq && (
            <PrerequisiteState to={confirmPrereq.to} message={confirmPrereq.message} />
          )}

          {lowConfidenceCount > 0 && (
            <p className="notice notice--preview">
              <strong>
                {lowConfidenceCount} row{lowConfidenceCount === 1 ? '' : 's'} flagged.
              </strong>{' '}
              The reader was unsure about these — they are marked below. Check them before
              confirming.
            </p>
          )}

          {rows.length === 0 ? (
            <EmptyState
              title="Nothing was read from that file"
              body="No courses could be extracted. The PDF may be a scanned image rather than text. Try another file, or add your courses by hand below."
              action={
                <button
                  type="button"
                  className="button button--secondary button--auto"
                  onClick={() => setRows([{ id: nextRowId++, courseCode: '', courseName: '', grade: '', lowConfidence: false, warnings: [] }])}
                >
                  Add a course
                </button>
              }
            />
          ) : (
            <div className="tablewrap">
              <table className="table">
                <caption className="visually-hidden">
                  Courses read from your transcript. Edit any cell to correct it.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Code</th>
                    <th scope="col">Course</th>
                    <th scope="col">Grade</th>
                    <th scope="col">Read</th>
                    <th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className={row.lowConfidence ? 'table__row--flagged' : undefined}>
                      <td data-label="Code">
                        <input
                          className="cell"
                          value={row.courseCode}
                          aria-label="Course code"
                          onChange={(e) => patch(row.id, { courseCode: e.target.value })}
                        />
                      </td>
                      <td data-label="Course">
                        <input
                          className={`cell${row.courseName.trim() ? '' : ' cell--missing'}`}
                          value={row.courseName}
                          aria-label="Course name"
                          onChange={(e) => patch(row.id, { courseName: e.target.value })}
                        />
                      </td>
                      <td data-label="Grade">
                        <input
                          className={`cell cell--narrow${row.grade.trim() ? '' : ' cell--missing'}`}
                          value={row.grade}
                          aria-label="Grade"
                          onChange={(e) => patch(row.id, { grade: e.target.value })}
                        />
                      </td>
                      <td data-label="Read">
                        {row.lowConfidence ? (
                          <span
                            className="badge badge--moderate"
                            title={row.warnings.join(' ') || 'The reader was unsure about this row.'}
                          >
                            Check
                          </span>
                        ) : (
                          <span className="cell__quiet">
                            {/* Confidence is a 0..1 fraction here — the one score in the API
                                that is not already a percentage. */}
                            {formatConfidence(row.confidence)}
                          </span>
                        )}
                      </td>
                      <td data-label="">
                        <button
                          type="button"
                          className="button button--quiet button--small"
                          onClick={() => setRows((c) => c?.filter((r) => r.id !== row.id) ?? c)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="actions">
            <button
              type="button"
              className="button button--secondary button--auto"
              onClick={() =>
                setRows((c) => [
                  ...(c ?? []),
                  { id: nextRowId++, courseCode: '', courseName: '', grade: '', lowConfidence: false, warnings: [] },
                ])
              }
            >
              Add a course
            </button>
            <button
              type="button"
              className="button button--primary button--auto"
              onClick={() => void handleConfirm()}
              disabled={confirm.running || usableCount === 0}
            >
              {confirm.running ? 'Building your profile…' : 'Confirm and build my profile'}
            </button>
            <span className="actions__hint">
              {usableCount} course{usableCount === 1 ? '' : 's'} will be saved
              {incomplete > 0 && ` — ${incomplete} incomplete row${incomplete === 1 ? '' : 's'} will be skipped`}.
            </span>
          </div>
        </>
      )}
    </AppShell>
  );
}
