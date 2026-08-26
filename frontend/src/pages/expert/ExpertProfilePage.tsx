import { useState } from 'react';
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Card, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as expertApi from '../../api/expert';
import { messageFor } from '../../api/errors';

export function ExpertProfilePage() {
  const { session } = useAuth();
  const token = session!.token;
  
  const profile = useAsync(() => expertApi.getProfile(token), [token]);
  const updateStatus = useAction(expertApi.setActive);

  const [successMsg, setSuccessMsg] = useState('');

  const handleToggleStatus = async () => {
    if (!profile.data) return;
    const isActive = profile.data.statusName === 'Active';
    const res = await updateStatus.run(token, !isActive);
    if (res) {
      profile.setData(res);
      setSuccessMsg(`Profile is now ${res.statusName}.`);
      setTimeout(() => setSuccessMsg(''), 5000);
    }
  };

  const isLoading = profile.loading;
  const isFailed = profile.failed;

  return (
    <AppShell>
      <PageHeader title="My Profile" lede="View your expert profile information." />

      {updateStatus.failed && (
        <Banner message={messageFor(updateStatus.error)} />
      )}

      {isLoading && <Skeleton rows={6} />}
      {!isLoading && isFailed && (
        <ErrorState message={messageFor(profile.error)} onRetry={profile.reload} />
      )}
      
      {!isLoading && !isFailed && profile.data && (
        <div className="stack stack--large">
          <Card as="section">
            <h2 className="section__title">Personal Information</h2>
            <dl className="facts">
              <dt>Name</dt>
              <dd>{profile.data.firstName} {profile.data.lastName}</dd>
              
              <dt>Email</dt>
              <dd>{profile.data.email}</dd>
              
              <dt>Study Field</dt>
              <dd>{profile.data.studyFieldName || 'Not specified'}</dd>
              
              <dt>Field Starting Year</dt>
              <dd>{profile.data.fieldStartingYear}</dd>

              <dt>Status</dt>
              <dd>
                <span className={`badge badge--${profile.data.statusName === "Active" ? "strong" : "weak"}`}>{profile.data.statusName}</span> 
                <span style={{ marginLeft: '0.5rem' }}>{profile.data.statusName}</span>
              </dd>
            </dl>
            <div className="notice notice--info" style={{ marginTop: '1rem' }}>
              Your name, email and study field are set by an administrator and cannot be changed here.
            </div>
          </Card>

          <Card as="section">
            <h2 className="section__title">Profile Visibility</h2>
            <p>
              Your current status is <strong>{profile.data.statusName}</strong>. 
              Only Active mentors appear to students browsing their field.
            </p>
            
            {successMsg && (
              <div className="notice notice--ok" style={{ margin: '1rem 0' }}>
                {successMsg}
              </div>
            )}

            <div className="actions" style={{ marginTop: '1.5rem' }}>
              <button 
                className={`button ${profile.data.statusName === 'Active' ? 'button--danger' : 'button--primary'}`}
                onClick={handleToggleStatus}
                disabled={updateStatus.running}
              >
                {profile.data.statusName === 'Active' ? 'Deactivate Profile' : 'Activate Profile'}
              </button>
            </div>
          </Card>
        </div>
      )}
    </AppShell>
  );
}
