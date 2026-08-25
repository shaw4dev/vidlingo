// Sign in / sign up.
//
// Two things this page has to get right beyond the obvious. First, there is a
// way out: browsing is public, so a visitor who does not want an account can
// leave with one click instead of bouncing off the domain. Second, the sign-up
// form validates as you type rather than only on submit — a mismatched
// confirmation discovered after a round trip is the worst time to discover it.
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../lib/api'
import { PasswordField } from '../components/PasswordField'

const MIN_PASSWORD = 8

export function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Where the guard sent us from, so signing in returns there instead of home.
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const registering = mode === 'register'
  const mismatch = registering && confirm.length > 0 && confirm !== password
  const tooShort = registering && password.length > 0 && password.length < MIN_PASSWORD

  const canSubmit = useMemo(() => {
    if (busy || username.length < 3 || password.length === 0) return false
    if (!registering) return true
    return password.length >= MIN_PASSWORD && confirm === password && email.includes('@')
  }, [busy, username, password, confirm, email, registering])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (registering) await register(username, email, password)
      else await login(username, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function switchMode() {
    setMode(registering ? 'login' : 'register')
    setError(null)
    setConfirm('')
  }

  return (
    <div className="auth-page">
      <main className="auth-card">
        <Link to="/" className="auth-brand">
          VidLingo
        </Link>
        <h1 className="auth-title">{registering ? 'Create your account' : 'Welcome back'}</h1>
        <p className="auth-sub">
          {registering
            ? 'Your saved words follow you across devices.'
            : 'Sign in to pick up your vocabulary where you left off.'}
        </p>

        <form onSubmit={onSubmit} noValidate>
          <label className="field">
            <span className="field-label">Username</span>
            <span className="field-control">
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                minLength={3}
                required
              />
            </span>
            {registering && (
              <span className="field-hint">Letters, numbers, dots, dashes. 3+ characters.</span>
            )}
          </label>

          {registering && (
            <label className="field">
              <span className="field-label">Email</span>
              <span className="field-control">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  required
                />
              </span>
              <span className="field-hint">Used to recover your account. Nothing else.</span>
            </label>
          )}

          <PasswordField
            label="Password"
            value={password}
            onChange={setPassword}
            autoComplete={registering ? 'new-password' : 'current-password'}
            minLength={registering ? MIN_PASSWORD : undefined}
            invalid={tooShort}
            hint={
              registering
                ? tooShort
                  ? `${MIN_PASSWORD - password.length} more character${
                      MIN_PASSWORD - password.length === 1 ? '' : 's'
                    } to go`
                  : `At least ${MIN_PASSWORD} characters.`
                : undefined
            }
          />

          {registering && (
            <PasswordField
              label="Confirm password"
              value={confirm}
              onChange={setConfirm}
              autoComplete="new-password"
              invalid={mismatch}
              hint={mismatch ? "These don't match yet." : undefined}
            />
          )}

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary" disabled={!canSubmit}>
            {busy ? 'Working…' : registering ? 'Create account' : 'Log in'}
          </button>
        </form>

        {!registering && (
          <p className="auth-aside">
            Forgotten your password? Password recovery isn&apos;t available yet — you can change
            it from your account page once signed in.
          </p>
        )}

        <div className="auth-foot">
          <button type="button" className="link" onClick={switchMode}>
            {registering ? 'Already have an account? Log in' : 'New here? Create an account'}
          </button>
          <Link to="/" className="link">
            Browse without an account →
          </Link>
        </div>
      </main>
    </div>
  )
}
