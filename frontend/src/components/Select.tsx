import { useId, type SelectHTMLAttributes } from 'react';

interface Option {
  value: string | number;
  label: string;
}

interface Props extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id' | 'children'> {
  label: string;
  options: Option[];
  /** Shown as a disabled first entry when nothing is chosen yet. */
  placeholder?: string;
  error?: string;
  hint?: string;
  optional?: boolean;
}

export function Select({ label, options, placeholder, error, hint, optional, ...select }: Props) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {optional && <span className="field__optional">optional</span>}
      </label>
      <select
        {...select}
        id={id}
        className={`field__input field__input--select${error ? ' field__input--error' : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {message && (
        <p
          id={messageId}
          className={error ? 'field__error' : 'field__hint'}
          role={error ? 'alert' : undefined}
        >
          {message}
        </p>
      )}
    </div>
  );
}
