import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { Banner } from '../components/Banner';
import { RolePicker } from '../components/RolePicker';
import { TextArea } from '../components/TextArea';
import { TextField } from '../components/TextField';
import { ApiError } from '../api/client';
import * as authApi from '../api/auth';
import { useAuth } from '../auth/useAuth';
import { SIGNUP_ROLES, homeFor } from '../auth/roles';
import {
  MIN_PASSWORD_LENGTH,
  collect,
  maxLength,
  requiredText,
  validateEmail,
  validatePassword,
  type Errors,
} from '../auth/validate';
import type { Role, SelfRegisterRole } from '../types';

export function SignupPage() {
  const { session, signIn } = useAuth();
  const navigate = useNavigate();

  const [role, setRole] = useState<SelfRegisterRole>('JOB_SEEKER');

  // Student fields
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  // Employer fields
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('');
  const [companyDescription, setCompanyDescription] = useState('');
  // Shared
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (session) return <Navigate to={homeFor(session.role)} replace />;

  function validate(): Errors {
    const shared = {
      email: validateEmail(email),
      password: validatePassword(password),
      // Confirmation is ours alone — the API has no such field. It catches the typo
      // that would otherwise lock someone out of an account they just created.
      confirm: password && confirm !== password ? 'The two passwords do not match' : undefined,
    };

    if (role === 'JOB_SEEKER') {
      return collect({
        ...shared,
        firstName: requiredText(firstName, 'First name') ?? maxLength(firstName, 100, 'First name'),
        lastName: requiredText(lastName, 'Last name') ?? maxLength(lastName, 100, 'Last name'),
      });
    }

    return collect({
      ...shared,
      companyName:
        requiredText(companyName, 'Company name') ?? maxLength(companyName, 200, 'Company name'),
      industry: maxLength(industry, 150, 'Industry'),
      companyDescription: maxLength(companyDescription, 2000, 'Company description'),
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const auth =
        role === 'JOB_SEEKER'
          ? await authApi.registerJobSeeker({
              firstName: firstName.trim(),
              lastName: lastName.trim(),
              email: email.trim(),
              password,
            })
          : await authApi.registerEmployer({
              companyName: companyName.trim(),
              // Omit rather than send "" — these are optional, and an empty string is
              // a value the backend would store, not an absence.
              industry: industry.trim() || undefined,
              companyDescription: companyDescription.trim() || undefined,
              email: email.trim(),
              password,
            });

      // Registration returns a token, so there is no second sign-in step.
      signIn(auth);
      navigate(homeFor(auth.role), { replace: true });
    } catch (error) {
      handleFailure(error);
    } finally {
      setSubmitting(false);
    }
  }

  function handleFailure(error: unknown) {
    if (error instanceof ApiError) {
      if (error.code === 'VALIDATION_ERROR' && error.fieldErrors.length > 0) {
        setErrors(error.byField());
        return;
      }
      if (error.code === 'EMAIL_ALREADY_EXISTS') {
        setErrors((prev) => ({ ...prev, email: 'An account already uses this email' }));
        setFormError('That email is already registered. Sign in instead, or use another address.');
        return;
      }
      setFormError(error.message);
      return;
    }
    setFormError(error instanceof Error ? error.message : 'Something went wrong. Please try again.');
  }

  const isStudent = role === 'JOB_SEEKER';

  return (
    <AuthLayout
      title="Create your account"
      subtitle={
        isStudent
          ? 'Start with your transcript and see where you stand.'
          : 'Post roles and see candidates ranked by the skills they can evidence.'
      }
      footer={
        <>
          Already registered? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <form className="form" onSubmit={handleSubmit} noValidate>
        {formError && <Banner message={formError} />}

        <RolePicker
          legend="I am registering as"
          roles={SIGNUP_ROLES as Role[]}
          value={role}
          onChange={(next) => {
            setRole(next as SelfRegisterRole);
            setErrors({});
            setFormError(null);
          }}
          disabled={submitting}
        />

        <p className="note">
          Mentors, content managers and administrators do not register here — those accounts
          are created by an administrator. If that is you, <Link to="/login">sign in</Link>.
        </p>

        {isStudent ? (
          <div className="form__row">
            <TextField
              label="First name"
              name="firstName"
              autoComplete="given-name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              error={errors.firstName}
              disabled={submitting}
              maxLength={100}
              required
            />
            <TextField
              label="Last name"
              name="lastName"
              autoComplete="family-name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              error={errors.lastName}
              disabled={submitting}
              maxLength={100}
              required
            />
          </div>
        ) : (
          <>
            <TextField
              label="Company name"
              name="companyName"
              autoComplete="organization"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              error={errors.companyName}
              disabled={submitting}
              maxLength={200}
              required
            />
            <TextField
              label="Industry"
              name="industry"
              optional
              placeholder="Software, healthcare, logistics…"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              error={errors.industry}
              disabled={submitting}
              maxLength={150}
            />
          </>
        )}

        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="email"
          placeholder={isStudent ? 'you@university.edu' : 'you@company.com'}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          disabled={submitting}
          maxLength={255}
          required
        />

        <TextField
          label="Password"
          type={showPassword ? 'text' : 'password'}
          name="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          disabled={submitting}
          required
        />

        <TextField
          label="Confirm password"
          type={showPassword ? 'text' : 'password'}
          name="confirmPassword"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
          disabled={submitting}
          required
        />

        <label className="checkline">
          <input
            type="checkbox"
            checked={showPassword}
            onChange={(e) => setShowPassword(e.target.checked)}
            disabled={submitting}
          />
          Show passwords
        </label>

        {!isStudent && (
          <TextArea
            label="About the company"
            name="companyDescription"
            optional
            rows={3}
            placeholder="What the company does, and the kind of people it hires."
            value={companyDescription}
            onChange={(e) => setCompanyDescription(e.target.value)}
            error={errors.companyDescription}
            hint={`${companyDescription.length} / 2000`}
            disabled={submitting}
            maxLength={2000}
          />
        )}

        <button type="submit" className="button button--primary" disabled={submitting}>
          {submitting ? 'Creating your account…' : 'Create account'}
        </button>
      </form>
    </AuthLayout>
  );
}
