// The account page: who you are, what you've collected, and the one setting
// that exists (your password).
//
// Kept deliberately short. A settings page with three toggles that do nothing
// reads as less finished than a page with two facts and one working control.
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { PasswordField } from '../components/PasswordField'
import { useAuth } from '../auth/AuthContext'
import { api, ApiError } from '../lib/api'

const MIN_PASSWORD = 8

export function AccountPage() {
  const { user, logout } = useAuth()

  if (!user) return null

  return (
    <div className="page">
      <AppHeader />

      <div className="stack">
        <header className="page-head">
          <h1 className="page-title">Account</h1>
          <p className="muted">Signed in as {user.username}.</p>
        </header>

        <section className="panel">
          <dl className="detail-list">
            <div>
              <dt>Username</dt>
              <dd>{user.username}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{user.email ?? <span className="muted">Not set</span>}</dd>
            </div>
            <div>
              <dt>Member since</dt>
              <dd>
                {new Date(user.created_at).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </dd>
            </div>
            <div>
              <dt>Words saved</dt>
              <dd>
                <Link to="/vocab">
                  {user.vocab_count} {user.vocab_count === 1 ? 'word' : 'words'}
                </Link>
              </dd>
            </div>
          </dl>
        </section>

        <ChangePassword />

        <section className="panel">
          <h2 className="panel-title">Session</h2>
          <p className="muted small">
            Logging out clears the token stored in this browser. Your saved words stay on your
            account.
          </p>
          <button className="btn-quiet" onClick={logout}>
            Log out
          </button>
        </section>
      </div>
    </div>
  )
}

function ChangePassword() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const mismatch = confirm.length > 0 && confirm !== next
  const tooShort = next.length > 0 && next.length < MIN_PASSWORD
  const ready = !busy && current.length > 0 && next.length >= MIN_PASSWORD && confirm === next

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setDone(false)
    setBusy(true)
    try {
      await api.changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      setDone(true)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 403
            ? 'That current password is incorrect.'
            : err.message
          : 'Could not change your password.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Change password</h2>
      <form onSubmit={onSubmit} className="narrow-form" noValidate>
        <PasswordField
          label="Current password"
          value={current}
          onChange={setCurrent}
          autoComplete="current-password"
        />
        <PasswordField
          label="New password"
          value={next}
          onChange={setNext}
          autoComplete="new-password"
          minLength={MIN_PASSWORD}
          invalid={tooShort}
          hint={tooShort ? `At least ${MIN_PASSWORD} characters.` : undefined}
        />
        <PasswordField
          label="Confirm new password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          invalid={mismatch}
          hint={mismatch ? "These don't match yet." : undefined}
        />

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {done && (
          <p className="form-ok" role="status">
            Password changed. Use the new one next time you log in.
          </p>
        )}

        <button type="submit" className="btn-primary" disabled={!ready}>
          {busy ? 'Working…' : 'Change password'}
        </button>
      </form>
    </section>
  )
}
