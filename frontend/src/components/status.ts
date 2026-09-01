/** Skill classification, kept out of the component module so fast refresh stays clean. */
export type Classification = 'Strong' | 'Moderate' | 'Weak';

/**
 * The backend title-cases these before sending them, but the AI wire format is lowercase
 * and the conversion lives in one place on the Java side — so compare case-insensitively
 * rather than depending on that never changing.
 */
export function normalise(status: string | undefined): Classification | null {
  switch (status?.toLowerCase()) {
    case 'strong':
      return 'Strong';
    case 'moderate':
      return 'Moderate';
    case 'weak':
      return 'Weak';
    default:
      return null;
  }
}
