import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { formatPercent } from '../api/format';
import { normalise } from './status';

/* ---------------------------------------------------------------------------
   The small pieces every screen reuses. Kept in one file because each is a few
   lines and they are almost always imported together.
   --------------------------------------------------------------------------- */

export function PageHeader({
  title,
  lede,
  action,
}: {
  title: string;
  lede?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="pagehead">
      <div>
        <h1 className="pagehead__title">{title}</h1>
        {lede && <p className="pagehead__lede">{lede}</p>}
      </div>
      {action && <div className="pagehead__action">{action}</div>}
    </header>
  );
}

export function Card({
  children,
  className = '',
  as: Tag = 'div',
}: {
  children: ReactNode;
  className?: string;
  as?: 'div' | 'li' | 'section' | 'article';
}) {
  return <Tag className={`card ${className}`.trim()}>{children}</Tag>;
}

/**
 * Skill status. The text label is not decoration — colour alone fails NFR-USE-05 and
 * would leave the status invisible to a colour-blind reader, so the word always ships
 * with the colour.
 */
export function StatusBadge({ status }: { status?: string }) {
  const known = normalise(status);
  return (
    <span className={`badge badge--${known ? known.toLowerCase() : 'unknown'}`}>
      {known ?? 'Unrated'}
    </span>
  );
}

/**
 * A 0..100 bar. Every score the API returns is already a percentage — the backend does the
 * 0.0..1.0 conversion in one place — so this never multiplies.
 */
export function ProgressBar({
  value,
  status,
  label,
}: {
  value: number;
  status?: string;
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const known = normalise(status);
  return (
    <div className="bar">
      <div
        className="bar__track"
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? 'Score'}
      >
        <div
          className={`bar__fill${known ? ` bar__fill--${known.toLowerCase()}` : ''}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="bar__value">{formatPercent(value)}</span>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <h2 className="empty__title">{title}</h2>
      <p className="empty__body">{body}</p>
      {action && <div className="empty__action">{action}</div>}
    </div>
  );
}

/** Placeholder rows while something loads (NFR-USE-04). */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-live="polite">
      <span className="visually-hidden">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton__row" />
      ))}
    </div>
  );
}

/** A whole-screen failure, with the one thing that might fix it. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="empty empty--error" role="alert">
      <h2 className="empty__title">That didn’t work</h2>
      <p className="empty__body">{message}</p>
      {onRetry && (
        <div className="empty__action">
          <button type="button" className="button button--secondary" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * A missing earlier step, with the way to fix it. Shown instead of an error because the
 * user has done nothing wrong — they have just arrived out of order (NFR-USE-03).
 */
export function PrerequisiteState({ message, to }: { message: string; to: string }) {
  return (
    <div className="empty empty--prereq">
      <h2 className="empty__title">One step first</h2>
      <p className="empty__body">{message}</p>
      <div className="empty__action">
        <Link className="button button--primary" to={to}>
          Take me there
        </Link>
      </div>
    </div>
  );
}

/**
 * Marks results that are not real scores. Job matching and candidate ranking are descoped
 * from the AI contract, and the mock's numbers are a placeholder heuristic — presenting
 * them unlabelled would be presenting fiction as analysis.
 */
export function PreviewBadge({ children }: { children: ReactNode }) {
  return (
    <p className="notice notice--preview">
      <strong>Preview.</strong> {children}
    </p>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
      {hint && <span className="stat__hint">{hint}</span>}
    </div>
  );
}
