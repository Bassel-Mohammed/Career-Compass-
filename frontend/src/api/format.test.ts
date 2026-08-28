import { describe, expect, it } from 'vitest';
import { formatDateTime } from './format';

describe('formatDateTime', () => {
  it('renders appointment times using a 24-hour clock', () => {
    const displayed = formatDateTime('2026-09-01T14:30:00');

    expect(displayed).toContain('14:30');
    expect(displayed).not.toMatch(/\b(?:AM|PM)\b/i);
  });
});
