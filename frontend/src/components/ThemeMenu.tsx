import { useEffect, useRef, useState } from 'react';
import { THEMES, loadTheme, setTheme, type Theme } from '../theme';

/**
 * Settings control in the top bar — currently one setting, the colour theme.
 *
 * A popover rather than a straight toggle because there are three states, not two: `system` is
 * distinct from `light`, and collapsing them would silently pin a reader to light the first time
 * they touched the control.
 */
export function ThemeMenu() {
  const [open, setOpen] = useState(false);
  const [theme, setThemeState] = useState<Theme>(loadTheme);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  function choose(next: Theme) {
    setTheme(next);
    setThemeState(next);
    setOpen(false);
  }

  return (
    <div className="theme-menu" ref={containerRef}>
      <button
        type="button"
        className="topbar__icon"
        aria-label="Settings"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
          <path
            d="M12 2.6v2.2M12 19.2v2.2M21.4 12h-2.2M4.8 12H2.6M18.6 5.4l-1.6 1.6M7 17l-1.6 1.6M18.6 18.6L17 17M7 7 5.4 5.4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
      </button>

      {open && (
        <div className="theme-menu__panel" role="menu" aria-label="Colour theme">
          <p className="theme-menu__title">Theme</p>
          {THEMES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="menuitemradio"
              aria-checked={theme === option.value}
              className={`theme-menu__option${theme === option.value ? ' theme-menu__option--active' : ''}`}
              onClick={() => choose(option.value)}
            >
              <span className="theme-menu__label">
                {option.label}
                {/* The tick is not the only marker: aria-checked carries it for a screen
                    reader, and the active row is also outlined. */}
                {theme === option.value && <span aria-hidden="true">✓</span>}
              </span>
              <span className="theme-menu__hint">{option.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
