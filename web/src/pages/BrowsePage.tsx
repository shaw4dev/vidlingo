// Home / lesson browse (fleshed out in T15). For T11 it proves the loop:
// an authenticated user is shown, and lessons load from the content API.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type LessonSummary } from '../lib/api'
import { useAuth } from '../auth/AuthContext'

export function BrowsePage() {
  const { user, logout } = useAuth()
  const [lessons, setLessons] = useState<LessonSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listLessons()
      .then(setLessons)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load lessons'),
      )
  }, [])

  return (
    <div className="page">
      <header className="topbar">
        <strong>VidLingo</strong>
        <span className="spacer" />
        <span className="muted">{user?.username}</span>
        <button className="link" onClick={logout}>
          Log out
        </button>
      </header>

      <main>
        <h2>Lessons</h2>
        {error && <p className="error">{error}</p>}
        {!lessons && !error && <p className="muted">Loading…</p>}
        {lessons && lessons.length === 0 && (
          <p className="muted">
            No lessons yet — run the content pipeline (T08) to ingest some.
          </p>
        )}
        <ul className="lesson-list">
          {lessons?.map((l) => (
            <li key={l.id} className="card">
              <Link to={`/reader/${l.id}`}>
                <div className="lesson-title">{l.title}</div>
                <div className="muted small">
                  {l.theme}
                  {l.difficulty ? ` · ${l.difficulty}` : ''}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  )
}
