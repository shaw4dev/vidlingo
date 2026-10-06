// One nav for every page, so the five surfaces stay reachable from each other
// instead of dead-ending in a back button.
//
// The right-hand side is the only part that knows whether anyone is signed in.
// A visitor sees Review and Vocab too — they are part of the product, and
// hiding them hides the reason to make an account. Following one lands on the
// gate that explains it, which then returns here.
import { NavLink, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useReviewSummary } from '../features/review/useReviewSummary'

const TABS = [
  { to: '/', label: 'Explore', end: true },
  { to: '/library', label: 'Library', end: false },
  { to: '/shorts', label: 'Shorts', end: false },
  { to: '/review', label: 'Review', end: false },
  { to: '/vocab', label: 'Vocab', end: false },
]

export function AppHeader() {
  const { user, loading } = useAuth()
  // The tab is unconditional, like the others; only the count is auth-aware.
  // A visitor has nothing due, but hiding the tab would hide the reason to
  // make an account.
  const review = useReviewSummary()

  return (
    <header className="topbar">
      <NavLink to="/" className="brand">
        <span className="brand-mark" aria-hidden="true" />
        VidLingo
      </NavLink>
      <nav className="nav">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) => (isActive ? 'nav-tab active' : 'nav-tab')}
          >
            {t.label}
            {t.to === '/review' && review && review.scheduled_today > 0 && (
              <span className="nav-badge">{review.scheduled_today}</span>
            )}
          </NavLink>
        ))}
      </nav>
      <span className="spacer" />
      {loading ? null : user ? (
        <NavLink
          to="/account"
          className={({ isActive }) => (isActive ? 'account-link active' : 'account-link')}
        >
          <span className="avatar" aria-hidden="true">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
          <span className="hide-sm">{user.username}</span>
        </NavLink>
      ) : (
        <>
          <Link to="/login" className="btn-small quiet hide-sm">
            Log in
          </Link>
          <Link to="/login" state={{ mode: 'register' }} className="btn-small">
            Sign up free
          </Link>
        </>
      )}
    </header>
  )
}
