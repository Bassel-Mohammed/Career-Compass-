import { Link } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { homeFor } from '../auth/roles';

export function NotFoundPage() {
  const { session } = useAuth();
  const back = session ? homeFor(session.role) : '/login';

  return (
    <div className="shell">
      <main className="shell__body shell__body--center">
        <h1 className="shell__title">Page not found</h1>
        <p className="shell__lede">That address does not match anything in CareerCompass.</p>
        <Link className="button button--primary" to={back}>
          {session ? 'Back to your dashboard' : 'Go to sign in'}
        </Link>
      </main>
    </div>
  );
}
