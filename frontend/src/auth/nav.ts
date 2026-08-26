import type { Role } from '../types';

export interface NavItem {
  to: string;
  label: string;
  /** Inline SVG path data, drawn on a 24x24 viewBox. */
  icon: string;
}

const ICONS = {
  dashboard: 'M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6v-9h-6v9Zm0-16v5h6V4h-6Z',
  transcript: 'M6 2h7l5 5v15H6V2Zm7 1.5V8h4.5M8.5 12h7M8.5 15.5h7M8.5 19h4',
  courses: 'M12 3 2 8l10 5 10-5-10-5Zm-6 8v4.5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V11l-6 3-6-3Z',
  quiz: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 15.5a1.15 1.15 0 1 1 0-2.3 1.15 1.15 0 0 1 0 2.3ZM13 13.2V14h-2v-1.6c0-1.6 2.4-1.9 2.4-3.3A1.4 1.4 0 0 0 12 7.7a1.6 1.6 0 0 0-1.6 1.5h-2A3.6 3.6 0 0 1 12 5.7a3.4 3.4 0 0 1 3.4 3.4c0 2.1-2.4 2.4-2.4 4.1Z',
  jobs: 'M9 4h6v3h4a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4V4Zm2 2v1h2V6h-2ZM4 12h16',
  mentors: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 8a8 8 0 0 1 16 0',
  profile: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 8a8 8 0 0 1 16 0',
  postings: 'M4 5h16M4 10h16M4 15h10M4 20h7',
  calendar: 'M7 3v3m10-3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z',
  sessions: 'M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  upload: 'M12 16V4m0 0L8 8m4-4 4 4M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2',
  people: 'M9 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-7 8a7 7 0 0 1 14 0m1-14.5a3.5 3.5 0 0 1 0 7M18 20a7 7 0 0 0-2-4.9',
  library: 'M4 4h4v16H4V4Zm6 0h4v16h-4V4Zm7.5.5 3.6 15.1',
} as const;

/**
 * The side navigation, per actor. Each entry must correspond to a route the role is
 * actually allowed through — `ProtectedRoute` sends them to their own home otherwise,
 * which from a nav click looks like the app ignoring them.
 */
export const NAV: Record<Role, NavItem[]> = {
  JOB_SEEKER: [
    { to: '/dashboard', label: 'Skill dashboard', icon: ICONS.dashboard },
    { to: '/transcript', label: 'Transcript', icon: ICONS.transcript },
    { to: '/courses', label: 'Courses', icon: ICONS.courses },
    { to: '/quizzes', label: 'Quizzes', icon: ICONS.quiz },
    { to: '/jobs', label: 'Job matches', icon: ICONS.jobs },
    { to: '/mentors', label: 'Mentors', icon: ICONS.mentors },
    { to: '/profile', label: 'Profile', icon: ICONS.profile },
  ],
  EMPLOYER: [
    { to: '/employer', label: 'Job postings', icon: ICONS.postings },
    { to: '/employer/profile', label: 'Company profile', icon: ICONS.profile },
  ],
  EXPERT: [
    { to: '/expert', label: 'Sessions', icon: ICONS.sessions },
    { to: '/expert/availability', label: 'Availability', icon: ICONS.calendar },
    { to: '/expert/profile', label: 'My profile', icon: ICONS.profile },
  ],
  CONTENT_MANAGER: [
    { to: '/content', label: 'Learning outcomes', icon: ICONS.upload },
  ],
  ADMIN: [
    { to: '/admin', label: 'Content managers', icon: ICONS.people },
    { to: '/admin/mentors', label: 'Mentors', icon: ICONS.mentors },
    { to: '/admin/reference', label: 'Reference data', icon: ICONS.library },
  ],
};
