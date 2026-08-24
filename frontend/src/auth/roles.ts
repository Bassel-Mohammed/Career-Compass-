import type { Role, SelfRegisterRole } from '../types';

interface RoleInfo {
  /** What this actor is called on screen. */
  label: string;
  /** Where they land after signing in. */
  home: string;
  /** Shown under the role picker so a user can tell which one is theirs. */
  hint: string;
}

export const ROLES: Record<Role, RoleInfo> = {
  JOB_SEEKER: {
    label: 'Student',
    home: '/dashboard',
    hint: 'Upload your transcript, see your skill gaps, take quizzes and book a mentor.',
  },
  EMPLOYER: {
    label: 'Employer',
    home: '/employer',
    hint: 'Post jobs and review ranked candidates.',
  },
  EXPERT: {
    label: 'Mentor',
    home: '/expert',
    hint: 'Manage your availability and consultation requests.',
  },
  CONTENT_MANAGER: {
    label: 'Content manager',
    home: '/content',
    hint: 'Maintain career paths and upload learning outcomes.',
  },
  ADMIN: {
    label: 'Administrator',
    home: '/admin',
    hint: 'Manage accounts, universities and study fields.',
  },
};

/** Sign-in offers all five actors. */
export const LOGIN_ROLES: Role[] = [
  'JOB_SEEKER',
  'EMPLOYER',
  'EXPERT',
  'CONTENT_MANAGER',
  'ADMIN',
];

/**
 * Only these two can create their own account. Mentors, content managers and
 * administrators are registered for them — the backend exposes no /register route
 * for those roles at all, so offering the option here would be a dead end.
 */
export const SIGNUP_ROLES: SelfRegisterRole[] = ['JOB_SEEKER', 'EMPLOYER'];

export function homeFor(role: Role): string {
  return ROLES[role].home;
}
