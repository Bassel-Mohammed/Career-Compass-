import { useId, useRef, useState, type DragEvent } from 'react';

interface Props {
  /** Bytes. Checked here so an oversize file never leaves the browser (NFR-PERF-07). */
  maxBytes: number;
  onSelect: (file: File) => void;
  disabled?: boolean;
  label: string;
  hint: string;
}

/**
 * PDF picker with drag-and-drop.
 *
 * The type and size checks run before the upload starts, because both failures are things
 * the user can see and fix immediately — waiting for a 10MB round trip to be told the file
 * is 10MB is a worse version of the same message.
 */
export function FileDrop({ maxBytes, onSelect, disabled, label, hint }: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);

  function accept(file: File | undefined) {
    if (!file) return;

    // Some browsers report an empty type for a PDF, so fall back to the extension
    // rather than rejecting a file the backend would have accepted.
    const looksLikePdf =
      file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!looksLikePdf) {
      setRejected('That is not a PDF. Transcripts must be text-based PDF files.');
      return;
    }
    if (file.size > maxBytes) {
      const mb = (maxBytes / 1024 / 1024).toFixed(0);
      const actual = (file.size / 1024 / 1024).toFixed(1);
      setRejected(`That file is ${actual}MB. The limit is ${mb}MB.`);
      return;
    }
    setRejected(null);
    onSelect(file);
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    accept(event.dataTransfer.files[0]);
  }

  return (
    <div className="filedrop-wrap">
      <label
        htmlFor={inputId}
        className={`filedrop${dragging ? ' filedrop--over' : ''}${disabled ? ' filedrop--off' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" className="filedrop__icon">
          <path
            d="M12 16V4m0 0L8 8m4-4 4 4M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="filedrop__label">{label}</span>
        <span className="filedrop__hint">{hint}</span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="application/pdf,.pdf"
          disabled={disabled}
          className="visually-hidden"
          onChange={(e) => {
            accept(e.target.files?.[0]);
            // Let the same file be chosen again after a rejection.
            e.target.value = '';
          }}
        />
      </label>
      {rejected && (
        <p className="field__error" role="alert">
          {rejected}
        </p>
      )}
    </div>
  );
}
