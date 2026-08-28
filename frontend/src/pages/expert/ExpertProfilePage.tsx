
import { AppShell } from '../../components/AppShell';
import { Banner } from '../../components/Banner';
import { Card, ErrorState, PageHeader, Skeleton } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';
import { useAction, useAsync } from '../../hooks/useAsync';
import * as expertApi from '../../api/expert';
import { messageFor } from '../../api/errors';
import { ChangePasswordCard } from '../../components/ChangePasswordCard';

import { toast } from 'sonner';

export function ExpertProfilePage() {
  const { session } = useAuth();
  const token = session!.token;
  
  const profile = useAsync(() => expertApi.getProfile(token), [token]);
  const updateStatus = useAction(expertApi.setActive);

  const handleToggleStatus = async () => {
    if (!profile.data) return;
    const isActive = profile.data.statusName === 'Active';
    const res = await updateStatus.run(token, !isActive);
    if (res) {
      profile.setData(res);
      toast.success(`Profile is now ${res.statusName}`);
    } else {
      toast.error('Failed to change status');
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
              <div>
                <dt>Name</dt>
                <dd>{profile.data.firstName} {profile.data.lastName}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{profile.data.email}</dd>
              </div>
              <div>
                <dt>Study Field</dt>
                <dd>{profile.data.studyFieldName || 'Not specified'}</dd>
              </div>
              <div>
                <dt>Field Starting Year</dt>
                <dd>{profile.data.fieldStartingYear}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  <span className={`badge badge--${profile.data.statusName === "Active" ? "strong" : "weak"}`}>
                    {profile.data.statusName}
                  </span>
                </dd>
              </div>
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

      <ChangePasswordCard />
    </AppShell>
  );
}
