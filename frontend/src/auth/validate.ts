/**
 * Client-side checks that mirror the Bean Validation annotations on the Java DTOs.
 *
 * These exist to spare the user a round trip, not to replace the server's checks —
 * the backend re-validates everything, and its `fieldErrors` win whenever they arrive.
 */

/** Shared with the backend's PasswordPolicy length limits. */
export const MIN_PASSWORD_LENGTH = 8;
export const PASSWORD_HINT =
  '8–100 characters, including at least one letter and one symbol.';

export type Errors = Record<string, string>;

export function requiredText(value: string, label: string): string | undefined {
  if (!value.trim()) return `${label} is required`;
  return undefined;
}

export function validateEmail(email: string): string | undefined {
  if (!email.trim()) return 'Email is required';
  // Deliberately loose. The server holds the authoritative @Email check; being stricter
  // here would only reject addresses the backend would have accepted.
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    return 'Enter a valid email address, like you@university.edu';
  }
  return undefined;
}

export function validatePassword(password: string): string | undefined {
  if (!password) return 'Password is required';
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
  }
  if (password.length > 100) return 'Password must be 100 characters or fewer';
  if (!/[A-Za-z]/.test(password) || !/[^A-Za-z0-9\s]/.test(password)) {
    return 'Password must include at least one letter and one symbol';
  }
  return undefined;
}

export function maxLength(value: string, limit: number, label: string): string | undefined {
  if (value.length > limit) return `${label} must be ${limit} characters or fewer`;
  return undefined;
}

/** Drops the undefined entries so `Object.keys(...).length` means "has errors". */
export function collect(candidates: Record<string, string | undefined>): Errors {
  const errors: Errors = {};
  for (const [field, message] of Object.entries(candidates)) {
    if (message) errors[field] = message;
  }
  return errors;
}
