import { describe, expect, it } from 'vitest';
import { validatePassword } from './validate';

describe('validatePassword', () => {
  it('accepts a password with sufficient length, letters, and a symbol', () => {
    expect(validatePassword('StrongPass!')).toBeUndefined();
  });

  it('rejects an eight-digit numeric password', () => {
    expect(validatePassword('12345678')).toBe(
      'Password must include at least one letter and one symbol',
    );
  });

  it('rejects a password without a symbol', () => {
    expect(validatePassword('Password123')).toBe(
      'Password must include at least one letter and one symbol',
    );
  });
});
