import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../components/AuthLayout';
import { Banner } from '../components/Banner';
import { RolePicker } from '../components/RolePicker';
import { TextField } from '../components/TextField';
import { ApiError } from '../api/client';
import * as authApi from '../api/auth';
import { useAuth } from '../auth/useAuth';
import { LOGIN_ROLES, ROLES, homeFor } from '../auth/roles';
import { collect, validateEmail, type Errors } from '../auth/validate';
import type { Role } from '../types';

export function LoginPage() {
  const { session, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [role, setRole] = useState<Role>('JOB_SEEKER');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Already signed in — nothing to do here.
  if (session) return <Navigate to={homeFor(session.role)} replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);

    // Password is only checked for presence here. Length rules belong to registration;
    // applying them at sign-in would lock out any account created before they existed.
    const found = collect({
      email: validateEmail(email),
      password: password ? undefined : 'Password is required',
    });
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const auth = await authApi.login(role, { email: email.trim(), password });
      signIn(auth);
      // Prefer wherever the guard bounced them from, but only if their role may go there.
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? homeFor(auth.role), { replace: true });
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
      if (error.status === 401) {
        // The backend cannot tell "no such account" from "wrong password", and should
        // not: saying which would confirm to a stranger that an address is registered.
        // What it is worth saying is that the role picker also decides the endpoint.
        setFormError(
          `That email and password do not match a ${ROLES[role].label.toLowerCase()} account. ` +
            'Check the password — and check you picked the right account type above.',
        );
        return;
      }
      setFormError(error.message);
      return;
    }
    setFormError(error instanceof Error ? error.message : 'Something went wrong. Please try again.');
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Pick your account type, then enter your details."
      footer={
        <>
          New here? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      <form className="form" onSubmit={handleSubmit} noValidate>
        {formError && <Banner message={formError} />}

        <RolePicker
          legend="I am signing in as"
          roles={LOGIN_ROLES}
          value={role}
          onChange={(next) => {
            setRole(next);
            setFormError(null);
          }}
          disabled={submitting}
        />

        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          placeholder="you@university.edu"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          disabled={submitting}
          required
        />

        <TextField
          label="Password"
          type={showPassword ? 'text' : 'password'}
          name="password"
          autoComplete="current-password"
          placeholder="Your password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
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
          Show password
        </label>

        <button type="submit" className="button button--primary" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  );
}
