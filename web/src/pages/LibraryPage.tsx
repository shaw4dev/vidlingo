// The library: a YouTube-style grid of everything in the corpus.
//
// This replaced a full-bleed snap-scrolling feed as the landing page. The feed
// still exists (/shorts) and is the better *study* surface, but it is a poor
// *browse* surface: one video per screen, captions inline, and long caption
// text fighting the snap points. Browsing wants density — thumbnail, title,
// length, difficulty — and captions only after she has chosen something.
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import {
  DIFFICULTIES,
  formatDuration,
  thumbnailUrl,
  useLessons,
  type Difficulty,
} from '../features/library/useLessons'
import type { LessonSummary } from '../lib/api'

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: 'Easy',
  medium: 'Medium',
  hard: 'Hard',
}

export function LibraryPage() {
  const { lessons, error } = useLessons()
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null)
  const [theme, setTheme] = useState<string | null>(null)

  const themes = useMemo(
    () => [...new Set(lessons?.map((l) => l.theme) ?? [])].sort(),
    [lessons],
  )

  const shown = useMemo(
    () =>
      (lessons ?? []).filter(
        (l) =>
          (difficulty == null || l.difficulty === difficulty) &&
          (theme == null || l.theme === theme),
      ),
    [lessons, difficulty, theme],
  )

  return (
    <div className="page wide">
      <AppHeader />

      <div className="filters">
        <Chip active={difficulty == null} onClick={() => setDifficulty(null)}>
          All levels
        </Chip>
        {DIFFICULTIES.map((d) => (
          <Chip key={d} active={difficulty === d} onClick={() => setDifficulty(d)}>
            {DIFFICULTY_LABELS[d]}
          </Chip>
        ))}
        {themes.length > 1 && <span className="filter-sep" />}
        {themes.length > 1 &&
          themes.map((t) => (
            <Chip
              key={t}
              active={theme === t}
              onClick={() => setTheme(theme === t ? null : t)}
            >
              {t.replace(/_/g, ' ')}
            </Chip>
          ))}
      </div>

      {error && <p className="error">{error}</p>}
      {!lessons && !error && <p className="muted">Loading…</p>}
      {lessons && shown.length === 0 && (
        <p className="muted">Nothing at this level yet — try another filter.</p>
      )}

      <div className="grid">
        {shown.map((lesson) => (
          <LessonCard key={lesson.id} lesson={lesson} />
        ))}
      </div>
    </div>
  )
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button className={active ? 'filter-chip on' : 'filter-chip'} onClick={onClick}>
      {children}
    </button>
  )
}

function LessonCard({ lesson }: { lesson: LessonSummary }) {
  const thumb = thumbnailUrl(lesson.youtube_id)
  return (
    <Link to={`/reader/${lesson.id}`} className="lesson-card">
      <div className="thumb" style={thumb ? { backgroundImage: `url(${thumb})` } : undefined}>
        <span className="thumb-duration">{formatDuration(lesson.duration_ms)}</span>
      </div>
      <div className="lesson-card-body">
        <div className="lesson-card-title">{lesson.title}</div>
        <div className="lesson-card-meta">
          {lesson.difficulty && (
            <span className={`level level-${lesson.difficulty}`}>
              {DIFFICULTY_LABELS[lesson.difficulty as Difficulty] ?? lesson.difficulty}
            </span>
          )}
          <span className="muted small">{lesson.theme.replace(/_/g, ' ')}</span>
        </div>
      </div>
    </Link>
  )
}
