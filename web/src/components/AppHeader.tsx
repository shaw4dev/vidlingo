// One nav for every page, so the four surfaces (library, shorts, vocab, reader)
// stay reachable from each other instead of dead-ending in a back button.
import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const TABS = [
  { to: '/', label: 'Library', end: true },
  { to: '/shorts', label: 'Shorts', end: false },
  { to: '/vocab', label: 'Vocab', end: false },
]

export function AppHeader() {
  const { user, logout } = useAuth()
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
      {user && <span className="muted small hide-sm">{user.username}</span>}
      <button className="link" onClick={logout}>
        Log out
      </button>
    </header>
  )
}
