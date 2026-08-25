// Auth state: holds the current user, exposes login/register/logout.
// Token lives in localStorage (api.ts tokenStore); on load we resolve it to a
// user via GET /auth/me — that's the authenticated call proving the flow works.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, tokenStore, type User } from '../lib/api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  refresh: () => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // Resolve an existing token to a user on first load.
  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  const finishAuth = useCallback(async (token: string) => {
    tokenStore.set(token)
    setUser(await api.me())
  }, [])

  const login = useCallback(
    async (username: string, password: string) => {
      const { access_token } = await api.login(username, password)
      await finishAuth(access_token)
    },
    [finishAuth],
  )

  const register = useCallback(
    async (username: string, email: string, password: string) => {
      const { access_token } = await api.register(username, email, password)
      await finishAuth(access_token)
    },
    [finishAuth],
  )

  /** Re-read the profile — the saved-word count on the account page goes stale
   *  the moment she saves a word anywhere else in the app. */
  const refresh = useCallback(async () => {
    if (tokenStore.get()) setUser(await api.me())
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh }),
    [user, loading, login, register, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
