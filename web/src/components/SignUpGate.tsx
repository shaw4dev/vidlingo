// What a signed-out visitor sees where an account is genuinely required.
//
// The old guard bounced straight to /login. That is correct and useless: it
// answers "you may not" without answering "why would I?", and it throws away
// the one moment when the person is demonstrably interested — they clicked
// Review, so they want to know what Review is.
//
// So the gate stays on the page, names what is behind it, and carries the
// destination into the login form so signing in lands where they were going.
import { Link, useLocation } from 'react-router-dom'
import { AppHeader } from './AppHeader'

export interface GateCopy {
  title: string
  sub: string
  /** Three concrete things the account unlocks, not three adjectives. */
  points: string[]
}

export function SignUpGate({ title, sub, points }: GateCopy) {
  const location = useLocation()
  const from = location.pathname + location.search

  return (
    <div className="page">
      <AppHeader />
      <section className="gate">
        <span className="gate-badge">Free account</span>
        <h1 className="gate-title">{title}</h1>
        <p className="gate-sub">{sub}</p>
        <ul className="gate-points">
          {points.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        <div className="gate-actions">
          <Link to="/login" state={{ from, mode: 'register' }} className="btn-hero">
            Create a free account
          </Link>
          <Link to="/login" state={{ from }} className="btn-hero ghost">
            I already have one
          </Link>
        </div>
        <p className="muted small gate-foot">
          Watching, looking words up and the whole player stay free without one —{' '}
          <Link className="link" to="/">
            keep browsing
          </Link>
          .
        </p>
      </section>
    </div>
  )
}
