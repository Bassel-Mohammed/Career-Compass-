import { useState, type ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { ROLES } from '../auth/roles';
import { NAV } from '../auth/nav';

interface Props {
  children: ReactNode;
  /** The career path chip in the top bar — students only, and only once one is chosen. */
  careerPath?: string;
}

/**
 * The shell every signed-in screen sits in: top bar, side navigation, content.
 *
 * Below 900px the side navigation becomes a drawer behind a menu button rather than
 * disappearing — the nav is the only way to reach most screens, so hiding it outright
 * would strand a phone user (NFR-USE-02).
 */
export function AppShell({ children, careerPath }: Props) {
  const { session, signOut } = useAuth();
  const [navOpen, setNavOpen] = useState(false);

  if (!session) return null;

  const items = NAV[session.role];
  const roleLabel = ROLES[session.role].label;

  return (
    <div className="app">
      <header className="topbar">
        <button
          type="button"
          className="topbar__menu"
          aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={navOpen}
          onClick={() => setNavOpen((open) => !open)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d={navOpen ? 'M6 6l12 12M18 6 6 18' : 'M4 7h16M4 12h16M4 17h16'}
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              fill="none"
            />
          </svg>
        </button>

        <Link to="/" className="brand brand--small">
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

        {careerPath && (
          <span className="topbar__path" title="Everything is measured against this career path">
            {careerPath}
          </span>
        )}

        <div className="topbar__account">
          <span className="pill">{roleLabel}</span>
          <span className="topbar__email">{session.email}</span>
          <button type="button" className="button button--quiet" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </header>

      <div className="app__body">
        {/* Click-away layer, drawer only. Hidden from assistive tech: the close
            button in the top bar is the labelled way out. */}
        {navOpen && <div className="app__scrim" onClick={() => setNavOpen(false)} aria-hidden="true" />}

        <nav className={`sidenav${navOpen ? ' sidenav--open' : ''}`} aria-label="Main">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              // `end` on the role's home route, or every deeper route would light it up too.
              end={item.to === '/employer' || item.to === '/expert' || item.to === '/content' || item.to === '/admin'}
              className={({ isActive }) => `sidenav__item${isActive ? ' sidenav__item--on' : ''}`}
              // On mobile the nav is a drawer over the content; leaving it open on top of
              // the page you just asked for would hide it.
              onClick={() => setNavOpen(false)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" className="sidenav__icon">
                <path
                  d={item.icon}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <main className="content">{children}</main>
      </div>
    </div>
  );
}
