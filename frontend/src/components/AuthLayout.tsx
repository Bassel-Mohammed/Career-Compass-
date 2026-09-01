import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface Props {
  title: string;
  subtitle: string;
  children: ReactNode;
  /** The "already have an account?" line under the card. */
  footer: ReactNode;
}

/**
 * The shell both sign-in and sign-up sit in: a panel that says what CareerCompass is
 * for, and the form beside it. The panel collapses away below the form on narrow
 * screens rather than being hidden, so the pitch survives on a phone.
 */
export function AuthLayout({ title, subtitle, children, footer }: Props) {
  return (
    <div className="auth">
      <aside className="auth__pitch">
        <Link to="/" className="brand">
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
        </Link>

        <h2 className="auth__pitch-title">
          Find out what your degree has actually taught you.
        </h2>
        <p className="auth__pitch-body">
          Upload your transcript and CareerCompass reads the skills behind your coursework,
          measures them against the career you are aiming for, and shows you exactly what is
          missing — with the courses, quizzes and mentors to close the gap.
        </p>

        <ul className="auth__steps">
          <li>
            <strong>Upload your transcript</strong>
            Your courses become a skill profile, not just a list of grades.
          </li>
          <li>
            <strong>See the gap</strong>
            Measured against 771 real requirements across nine career paths.
          </li>
          <li>
            <strong>Close it</strong>
            Recommended courses, skill quizzes and mentors matched to what you lack.
          </li>
        </ul>
      </aside>

      <main className="auth__panel">
        <div className="auth__card">
          <h1 className="auth__title">{title}</h1>
          <p className="auth__subtitle">{subtitle}</p>
          {children}
        </div>
        <p className="auth__footer">{footer}</p>
      </main>
    </div>
  );
}
