import { request } from './client';
import type {
  AuthResponse,
  LoginRequest,
  RegisterEmployerRequest,
  RegisterJobSeekerRequest,
  Role,
  SelfRegisterRole,
} from '../types';

/**
 * Login is per-actor: LoginRequest carries no role field, so the URL is the only
 * thing that says which table to look in. Picking the wrong one for a real account
 * gives 401, not a redirect — which is why the sign-in form asks up front.
 */
const LOGIN_PATH: Record<Role, string> = {
  JOB_SEEKER: '/api/auth/job-seekers/login',
  EMPLOYER: '/api/auth/employers/login',
  EXPERT: '/api/auth/experts/login',
  CONTENT_MANAGER: '/api/auth/content-managers/login',
  ADMIN: '/api/auth/admins/login',
};

const REGISTER_PATH: Record<SelfRegisterRole, string> = {
  JOB_SEEKER: '/api/auth/job-seekers/register',
  EMPLOYER: '/api/auth/employers/register',
};

/** Sign in as `role`. 200 on success, 401 INVALID_CREDENTIALS otherwise. */
export function login(role: Role, credentials: LoginRequest): Promise<AuthResponse> {
  return request<AuthResponse>(LOGIN_PATH[role], { method: 'POST', body: credentials });
}

/** Create a job seeker account. 201 on success; 409 EMAIL_ALREADY_EXISTS if taken. */
export function registerJobSeeker(body: RegisterJobSeekerRequest): Promise<AuthResponse> {
  return request<AuthResponse>(REGISTER_PATH.JOB_SEEKER, { method: 'POST', body });
}

/** Create an employer account. 201 on success; 409 EMAIL_ALREADY_EXISTS if taken. */
export function registerEmployer(body: RegisterEmployerRequest): Promise<AuthResponse> {
  return request<AuthResponse>(REGISTER_PATH.EMPLOYER, { method: 'POST', body });
}

/**
 * End the session. One endpoint for all five actors — the token already says who is
 * calling. It must actually be sent: the backend adds the token to a denylist, so a
 * copy taken before logout stops working. Clearing local storage alone would not do that.
 */
export function logout(token: string): Promise<void> {
  return request<void>('/api/auth/logout', { method: 'POST', token });
}
