// Gate routes behind auth: while resolving the token show nothing, then either
// render the children or make the case for an account.
//
// Routes that need a person but have nothing to advertise (the account page —
// you cannot want an account page before you have an account) still redirect;
// routes that are part of the pitch render SignUpGate in place instead, so the
// URL survives and the sign-up form knows where to return.
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { SignUpGate, type GateCopy } from './SignUpGate'
import type { ReactNode } from 'react'

export function ProtectedRoute({
  children,
  gate,
}: {
  children: ReactNode
  /** Copy for the in-place gate; omitted means redirect to the login page. */
  gate?: GateCopy
}) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="center muted">Loading…</div>
  if (!user) {
    if (gate) return <SignUpGate {...gate} />
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  return <>{children}</>
}
