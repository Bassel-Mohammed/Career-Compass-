import { useId, type TextareaHTMLAttributes } from 'react';

interface Props extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> {
  label: string;
  error?: string;
  hint?: string;
  optional?: boolean;
}

export function TextArea({ label, error, hint, optional, ...textarea }: Props) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;

  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {optional && <span className="field__optional">optional</span>}
      </label>
      <textarea
        {...textarea}
        id={id}
        className={`field__input field__input--area${error ? ' field__input--error' : ''}`}
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
