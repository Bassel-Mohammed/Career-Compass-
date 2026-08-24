import { useAuth } from '../auth/useAuth';
import { ROLES } from '../auth/roles';
import type { Role } from '../types';

/**
 * What each actor's home will hold once it is built. Listed here rather than left blank
 * so the signed-in state is verifiable end to end — you can see which role the token
 * actually carried — and so the next screen to build is named on the screen itself.
 */
const NEXT_UP: Record<Role, string[]> = {
  JOB_SEEKER: [
    'Upload a transcript and watch it parse',
    'Skill profile and the gap against a chosen career path',
    'Recommended courses for each missing skill',
    'Skill quizzes',
    'Mentor matches and consultation booking',
  ],
  EMPLOYER: ['Post a job', 'Manage open postings', 'Ranked candidates per posting'],
  EXPERT: ['Availability calendar', 'Incoming consultation requests', 'Past consultations'],
  CONTENT_MANAGER: ['Career paths', 'Upload learning outcomes', 'Course catalog coverage'],
  ADMIN: ['Content manager accounts', 'Universities and study fields', 'Platform overview'],
};

export function PlaceholderHome() {
  const { session, signOut } = useAuth();
  if (!session) return null; // ProtectedRoute guarantees this; narrowing for TypeScript.

  const info = ROLES[session.role];
  // An absolute time rather than "in N minutes": expiresAt is fixed, so this stays
  // correct however long the page sits open, and needs no clock read during render.
  const expiresAt = new Date(session.expiresAt).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className="shell">
      <header className="shell__bar">
        <span className="brand brand--small">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.6" />
              <path
                d="M15.4 8.6 13.7 13.7 8.6 15.4l1.7-5.1 5.1-1.7Z"
                fill="currentColor"
                fillOpacity=".25"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          CareerCompass
        </span>
        <div className="shell__account">
          <span className="pill">{info.label}</span>
          <span className="shell__email">{session.email}</span>
          <button type="button" className="button button--quiet" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="shell__body">
        <h1 className="shell__title">Signed in as a {info.label.toLowerCase()}</h1>
        <p className="shell__lede">{info.hint}</p>

        <dl className="facts">
          <div>
            <dt>Role</dt>
            <dd>{session.role}</dd>
          </div>
          <div>
            <dt>User id</dt>
            <dd>{session.userId}</dd>
          </div>
          <div>
            <dt>Session expires at</dt>
            <dd>{expiresAt}</dd>
          </div>
        </dl>

        <section className="todo">
          <h2 className="todo__title">Not built yet — what belongs here</h2>
          <ul>
            {NEXT_UP[session.role].map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
