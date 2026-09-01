import { AppShell } from '../../components/AppShell';
import { ChangePasswordCard } from '../../components/ChangePasswordCard';
import { Card, PageHeader } from '../../components/ui';
import { useAuth } from '../../auth/useAuth';

/**
 * The administrator's own account.
 *
 * Every other actor reaches password rotation from a profile screen they already had; the
 * administrator had none, which left the single most privileged account in the system as the
 * only one that could not change its password. There is no admin self-service API beyond
 * this, so the page is deliberately thin — it exists for the credential, not for editing an
 * identity that is provisioned outside the application.
 */
export function AdminProfilePage() {
  const { session } = useAuth();

  return (
    <AppShell>
      <PageHeader title="My account" lede="Your administrator sign-in." />

      <Card>
        <h2 className="section__title">Account</h2>
        <dl className="detail-grid">
          <div>
            <dt className="detail-grid__label">Email</dt>
            <dd className="detail-grid__value">{session!.email}</dd>
          </div>
          <div>
            <dt className="detail-grid__label">Role</dt>
            <dd className="detail-grid__value">Administrator</dd>
          </div>
        </dl>
        <p className="cell__quiet">
          Administrator accounts are provisioned outside the application and cannot be created
          or renamed through the API.
        </p>
      </Card>

      <ChangePasswordCard />
    </AppShell>
  );
}
