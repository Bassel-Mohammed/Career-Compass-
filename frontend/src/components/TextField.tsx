import { useId, type InputHTMLAttributes } from 'react';

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  /** Server- or client-side message for this field. Renders the input in its error state. */
  error?: string;
  /** Quiet guidance shown when there is no error to show instead. */
  hint?: string;
  /** Marks the field visually and for assistive technology. */
  optional?: boolean;
}

export function TextField({ label, error, hint, optional, ...input }: Props) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {optional && <span className="field__optional">optional</span>}
      </label>
      <input
        {...input}
        id={id}
        className={`field__input${error ? ' field__input--error' : ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
      />
      {message && (
        <p id={messageId} className={error ? 'field__error' : 'field__hint'} role={error ? 'alert' : undefined}>
          {message}
        </p>
      )}
    </div>
  );
}
