// A real 404 instead of a silent redirect home.
//
// Bouncing an unknown URL to the library hides typos and dead links: the
// visitor believes they arrived somewhere and cannot tell what went wrong.
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'

export function NotFoundPage() {
  return (
    <div className="page">
      <AppHeader />
      <div className="empty-state">
        <p className="empty-code">404</p>
        <h1 className="empty-title">That page doesn&apos;t exist</h1>
        <p className="muted">The link may be out of date, or the address mistyped.</p>
        <Link to="/" className="btn-primary">
          Go to the library
        </Link>
      </div>
    </div>
  )
}
