// One nav for every page, so the four surfaces (library, shorts, vocab, reader)
// stay reachable from each other instead of dead-ending in a back button.
//
// The right-hand side is the only part that knows whether anyone is signed in.
// A visitor sees Vocab too — it is part of the product, and hiding it hides the
// reason to make an account. Following it routes through the login page, which
// then returns here.
import { NavLink, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const TABS = [
  { to: '/', label: 'Library', end: true },
  { to: '/shorts', label: 'Shorts', end: false },
  { to: '/vocab', label: 'Vocab', end: false },
]

export function AppHeader() {
  const { user, loading } = useAuth()

  return (
    <header className="topbar">
      <NavLink to="/" className="brand">
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
        <Link to="/login" className="btn-small">
          Log in
        </Link>
      )}
    </header>
  )
}
