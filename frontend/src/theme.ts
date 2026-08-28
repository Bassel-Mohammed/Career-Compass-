/**
 * Colour theme: what the reader chose, and how the rest of the app hears about it.
 *
 * `system` is the default and is not the same as `light` — it means "follow the machine", so it
 * has no `data-theme` attribute at all and lets the `prefers-color-scheme` block in `index.css`
 * decide. Writing `data-theme="light"` for a reader who never asked for light would pin them to
 * light forever, including at night.
 */

export type Theme = 'system' | 'light' | 'dark';

export const THEMES: { value: Theme; label: string; hint: string }[] = [
  { value: 'system', label: 'System', hint: 'Follow your device setting' },
  { value: 'light', label: 'Light', hint: 'Always light' },
  { value: 'dark', label: 'Dark', hint: 'Always dark' },
];

const STORAGE_KEY = 'careercompass.theme';

/** Fires on `document` whenever the applied theme changes, so non-CSS consumers can repaint. */
export const THEME_CHANGE_EVENT = 'careercompass:themechange';

function isTheme(value: unknown): value is Theme {
  return value === 'system' || value === 'light' || value === 'dark';
}

/**
 * The stored choice, or `system`.
 *
 * Storage can throw outright — a private window, or a browser set to block site data — and a
 * theme preference is never worth failing a page load over.
 */
export function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isTheme(stored) ? stored : 'system';
  } catch {
    return 'system';
  }
}

/**
 * Put the choice on `<html>` and tell anything that cannot read CSS.
 *
 * The attribute is *removed* for `system` rather than set to a value: its absence is what lets
 * the media query apply.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', theme);
  }
  document.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: theme }));
}

/** Apply and remember. Storage failing must not stop the theme from taking effect. */
export function setTheme(theme: Theme): void {
  applyTheme(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Ignored: the theme is applied for this session, it just will not survive a reload.
  }
}

/** Whether dark is actually in force right now — the choice resolved against the device. */
export function resolvedTheme(theme: Theme = loadTheme()): 'light' | 'dark' {
  if (theme !== 'system') return theme;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
