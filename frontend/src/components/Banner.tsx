interface Props {
  /** Whole-form failure: bad credentials, taken email, server unreachable. */
  message: string;
}

/**
 * Announced with role="alert" so a screen reader hears the failure without the user
 * having to hunt for it — the message usually appears well above the submit button
 * they just pressed.
 */
export function Banner({ message }: Props) {
  return (
    <div className="banner banner--error" role="alert">
      <svg viewBox="0 0 20 20" aria-hidden="true" className="banner__icon">
        <path
          fill="currentColor"
          d="M10 1.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Zm0 4a1 1 0 0 1 1 1v4.25a1 1 0 1 1-2 0V6.5a1 1 0 0 1 1-1Zm0 9.75a1.15 1.15 0 1 1 0-2.3 1.15 1.15 0 0 1 0 2.3Z"
        />
      </svg>
      <span>{message}</span>
    </div>
  );
}
