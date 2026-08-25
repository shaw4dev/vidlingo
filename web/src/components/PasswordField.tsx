// A password input with a reveal toggle.
//
// Revealing is an accessibility feature before it is a convenience one: a long
// password typed blind on a phone keyboard is the single most common reason
// people abandon a sign-up. The button is a real <button type="button"> so it
// is reachable by keyboard and never submits the form by accident.
import { useId, useState } from 'react'

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  minLength,
  hint,
  invalid,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  autoComplete: string
  minLength?: number
  hint?: string
  invalid?: boolean
}) {
  const [shown, setShown] = useState(false)
  const hintId = useId()

  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <span className="field-control">
        <input
          type={shown ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          minLength={minLength}
          aria-invalid={invalid || undefined}
          aria-describedby={hint ? hintId : undefined}
          required
        />
        <button
          type="button"
          className="reveal"
          onClick={() => setShown((s) => !s)}
          aria-pressed={shown}
          aria-label={shown ? 'Hide password' : 'Show password'}
          title={shown ? 'Hide password' : 'Show password'}
        >
          <EyeIcon off={shown} />
        </button>
      </span>
      {hint && (
        <span className={invalid ? 'field-hint bad' : 'field-hint'} id={hintId}>
          {hint}
        </span>
      )}
    </label>
  )
}

/** Inline so there is no icon-font request and it inherits currentColor. */
function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M1.8 12S5.5 5.5 12 5.5 22.2 12 22.2 12 18.5 18.5 12 18.5 1.8 12 1.8 12Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3.1" fill="none" stroke="currentColor" strokeWidth="1.6" />
      {off && (
        <line
          x1="4"
          y1="20"
          x2="20"
          y2="4"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      )}
    </svg>
  )
}
