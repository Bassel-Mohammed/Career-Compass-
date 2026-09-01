import { screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '../test/utils';
import { LoginPage } from './LoginPage';
import * as authApi from '../api/auth';
import { ApiError } from '../api/client';

// Mock the API client
vi.mock('../api/auth', () => ({
  login: vi.fn(),
}));

// We also need to mock useLocation and useNavigate from react-router-dom
// Our custom render already wraps the component in BrowserRouter, so we don't
// mock the whole module, just the hooks if we need to spy on them.
// Alternatively, testing standard navigation can be done via memory router but our utils uses BrowserRouter.
// We'll rely on the actual router for basic rendering and mocking API responses.

describe('LoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.localStorage.clear();
  });

  it('renders all form elements', () => {
    render(<LoginPage />);

    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByText('I am signing in as')).toBeInTheDocument();
  });

  it('shows validation errors for empty fields', async () => {
    render(<LoginPage />);

    const submitBtn = screen.getByRole('button', { name: 'Sign in' });
    fireEvent.click(submitBtn);

    // Should show error messages without calling the API
    expect(await screen.findByText('Email is required')).toBeInTheDocument();
    expect(await screen.findByText('Password is required')).toBeInTheDocument();

    expect(authApi.login).not.toHaveBeenCalled();
  });

  it('calls API and logs in successfully', async () => {
    // Mock successful login response
    (authApi.login as any).mockResolvedValueOnce({
      token: 'fake-jwt-token',
      role: 'JOB_SEEKER',
      expiresInSeconds: 1800,
      jobSeeker: { firstName: 'John' },
    });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'student@test.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } });

    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith('JOB_SEEKER', {
        email: 'student@test.com',
        password: 'password123',
      });
    });
  });

  it('shows banner when API login fails with 401', async () => {
    // Mock failed login response
    (authApi.login as any).mockRejectedValueOnce(
      new ApiError(401, 'UNAUTHORIZED', 'Invalid credentials', [])
    );

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'wrong@test.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrongpass' } });

    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    // Expect the custom 401 error message for the specific role
    await waitFor(() => {
      expect(screen.getByText(/That email and password do not match a student account/)).toBeInTheDocument();
    });
  });
});
