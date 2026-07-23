// Reader placeholder — the player + tappable bilingual subtitles land in T12.
// For now it confirms routing + fetching a full lesson package works.
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type LessonDetail } from '../lib/api'

export function ReaderPage() {
  const { lessonId } = useParams<{ lessonId: string }>()
  const [lesson, setLesson] = useState<LessonDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!lessonId) return
    api
      .getLesson(lessonId)
      .then(setLesson)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load lesson'),
      )
  }, [lessonId])

  return (
    <div className="page">
      <header className="topbar">
        <Link to="/" className="link">
          ← Lessons
        </Link>
      </header>
      <main>
        {error && <p className="error">{error}</p>}
        {!lesson && !error && <p className="muted">Loading…</p>}
        {lesson && (
          <>
            <h2>{lesson.title}</h2>
            <p className="muted small">
              {lesson.sentences.length} sentences · player + subtitles coming in T12
            </p>
          </>
        )}
      </main>
    </div>
  )
}
