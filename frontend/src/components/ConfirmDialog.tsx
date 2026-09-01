import { useEffect, useRef } from 'react';

interface Props {
  title: string;
  body: string;
  confirmLabel: string;
  /** Styles the confirm button as destructive and makes it the non-default choice. */
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A modal confirmation for anything that cannot be undone.
 *
 * Built on <dialog> so the browser supplies the focus trap, the Escape handling and the
 * inert background — all things a hand-rolled overlay gets subtly wrong.
 */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  destructive,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className="dialog"
      // Escape and the backdrop both mean "cancel"; without this the dialog closes
      // natively while the component still thinks it is open.
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 className="dialog__title">{title}</h2>
      <p className="dialog__body">{body}</p>
      <div className="dialog__actions">
        <button type="button" className="button button--secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          type="button"
          className={`button ${destructive ? 'button--danger' : 'button--primary'}`}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? 'Working…' : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
