import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, StatusBadge } from '../../components/ui';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { TextArea } from '../../components/TextArea';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as expertApi from '../../api/expert';
import { messageFor } from '../../api/errors';
import { formatDateTime } from '../../api/format';
import type { AppointmentResponse } from '../../types';

export function ExpertSessionsPage() {
  const { session } = useAuth();
  const token = session!.token;
  
  const scheduled = useAsync(() => expertApi.listScheduled(token), [token]);
  const history = useAsync(() => expertApi.listHistory(token), [token]);
  
  const respond = useAction(expertApi.respondToRequest);
  const record = useAction(expertApi.recordOutcome);

  const [rejectId, setRejectId] = useState<number | null>(null);
  const [outcomeId, setOutcomeId] = useState<number | null>(null);
  const [notes, setNotes] = useState('');
  const [feedback, setFeedback] = useState('');

  /**
   * Every mutation here can move an appointment between the two lists, not just change it in
   * place: rejecting sends it to history, and recording an outcome completes it. Patching only
   * the list we happen to be looking at left the other one showing a stale copy of the same
   * session — the sessions screen would report it as both Accepted and Requested at once.
   * Refetching both is cheap and keeps them honest.
   */
  const refreshBothLists = () => {
    scheduled.reload();
    history.reload();
  };

  const handleAccept = async (id: number) => {
    const res = await respond.run(token, id, true);
    if (res) refreshBothLists();
  };

  const handleReject = async () => {
    if (!rejectId) return;
    const res = await respond.run(token, rejectId, false);
    if (res) {
      setRejectId(null);
      refreshBothLists();
    }
  };

  const handleOpenOutcome = (a: AppointmentResponse) => {
    setOutcomeId(a.appointmentId);
    setNotes(a.sessionNotes || '');
    setFeedback(a.feedback || '');
  };

  const handleSaveOutcome = async () => {
    if (!outcomeId) return;
    const res = await record.run(token, outcomeId, { sessionNotes: notes, feedback });
    if (res) {
      setOutcomeId(null);
      // Recording an outcome completes the session, so it leaves Upcoming for Past.
      refreshBothLists();
    }
  };

  const isLoading = scheduled.loading || history.loading;
  const isFailed = scheduled.failed || history.failed;
  const errorMsg = scheduled.error ? messageFor(scheduled.error) : history.error ? messageFor(history.error) : '';
  
  const getBadgeType = (status: string) => {
    switch (status) {
      case 'Requested': return 'unknown';
      case 'Accepted': return 'strong';
      case 'Rejected': return 'weak';
      case 'Completed': return 'moderate';
      default: return 'unknown';
    }
  };

  return (
    <AppShell>
      <PageHeader title="Consultation Sessions" lede="Manage your upcoming and past student mentoring sessions." />

      {(respond.failed || record.failed) && (
        <Banner message={messageFor(respond.error || record.error)} />
      )}

      {isLoading && <Skeleton rows={6} />}
      {!isLoading && isFailed && (
        <ErrorState message={errorMsg} onRetry={() => { scheduled.reload(); history.reload(); }} />
      )}
      
      {!isLoading && !isFailed && (
        <div className="stack stack--large">
          <section>
            <h2 className="section__title">Upcoming Sessions</h2>
            {scheduled.data?.length === 0 ? (
              <EmptyState title="No upcoming sessions" body="You don't have any scheduled sessions right now." />
            ) : (
              <ul className="list-reset stack">
                {scheduled.data?.map(app => (
                  <Card key={app.appointmentId} as="li" className="posting">
                    <div className="posting__head">
                      <h3 className="posting__title">
                        Session with <Link to={`/expert/job-seekers/${app.jobseekerId}`}>{app.jobseekerName}</Link>
                      </h3>
                      <StatusBadge status={getBadgeType(app.statusName) === 'unknown' ? 'Unknown' : app.statusName} />
                    </div>
                    <div className="posting__meta">
                      {formatDateTime(app.appointmentDate)} • Status: {app.statusName}
                    </div>

                    {app.statusName === 'Requested' && (
                      <div className="posting__actions stack stack--small">
                        <div className="actions">
                          <button 
                            className="button button--primary button--small" 
                            onClick={() => handleAccept(app.appointmentId)}
                            disabled={respond.running}
                          >
                            Accept
                          </button>
                          <button 
                            className="button button--danger button--small" 
                            onClick={() => setRejectId(app.appointmentId)}
                            disabled={respond.running}
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    )}

                    {(app.statusName === 'Accepted' || app.statusName === 'Completed') && outcomeId !== app.appointmentId && (
                      <div className="posting__actions stack stack--small">
                        {(app.sessionNotes || app.feedback) && (
                          <div className="notice notice--info stack stack--small">
                            {app.sessionNotes && (
                              <div>
                                <strong>Session Notes:</strong>
                                <p>{app.sessionNotes}</p>
                              </div>
                            )}
                            {app.feedback && (
                              <div>
                                <strong>Feedback:</strong>
                                <p>{app.feedback}</p>
                              </div>
                            )}
                          </div>
                        )}
                        <div className="actions">
                          <button 
                            className="button button--secondary button--small" 
                            onClick={() => handleOpenOutcome(app)}
                          >
                            {app.sessionNotes || app.feedback ? 'Edit outcome' : 'Record outcome'}
                          </button>
                        </div>
                      </div>
                    )}

                    {outcomeId === app.appointmentId && (
                      <div className="form stack stack--small">
                        <TextArea 
                          label="Session Notes" 
                          value={notes} 
                          onChange={e => setNotes(e.target.value)} 
                          placeholder="Internal notes for your reference"
                        />
                        <TextArea 
                          label="Student Feedback" 
                          value={feedback} 
                          onChange={e => setFeedback(e.target.value)} 
                          placeholder="Feedback shared with the student"
                        />
                        <div className="actions">
                          <button className="button button--primary" onClick={handleSaveOutcome} disabled={record.running}>Save Outcome</button>
                          <button className="button button--quiet" onClick={() => setOutcomeId(null)} disabled={record.running}>Cancel</button>
                        </div>
                      </div>
                    )}
                  </Card>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2 className="section__title">Past Sessions</h2>
            {history.data?.length === 0 ? (
              <EmptyState title="No past sessions" body="Your consultation history is empty." />
            ) : (
              <ul className="list-reset stack">
                {history.data?.map(app => (
                  <Card key={app.appointmentId} as="li" className="posting">
                    <div className="posting__head">
                      <h3 className="posting__title">
                        Session with <Link to={`/expert/job-seekers/${app.jobseekerId}`}>{app.jobseekerName}</Link>
                      </h3>
                      <StatusBadge status={app.statusName} />
                    </div>
                    <div className="posting__meta">
                      {formatDateTime(app.appointmentDate)} • Status: {app.statusName}
                    </div>

                    {(app.sessionNotes || app.feedback) && (
                      <div className="posting__actions stack stack--small">
                        <div className="notice notice--info stack stack--small">
                          {app.sessionNotes && (
                            <div>
                              <strong>Session Notes:</strong>
                              <p>{app.sessionNotes}</p>
                            </div>
                          )}
                          {app.feedback && (
                            <div>
                              <strong>Feedback:</strong>
                              <p>{app.feedback}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </Card>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {rejectId && (
        <ConfirmDialog
          title="Reject Request"
          body="Are you sure you want to reject this consultation request? The student will be notified."
          confirmLabel="Reject Request"
          destructive={true}
          busy={respond.running}
          onConfirm={handleReject}
          onCancel={() => setRejectId(null)}
        />
      )}
    </AppShell>
  );
}
