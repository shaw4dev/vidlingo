// The library: a YouTube-style grid of everything in the corpus.
//
// This replaced a full-bleed snap-scrolling feed as the landing page. The feed
// still exists (/shorts) and is the better *study* surface, but it is a poor
// *browse* surface: one video per screen, captions inline, and long caption
// text fighting the snap points. Browsing wants density — thumbnail, title,
// length, difficulty — and captions only after she has chosen something.
import { useEffect, useMemo, useState } from 'react'
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

/** How many cards to render before "Show more". A screenful and a bit, so the
 *  page has a visible bottom edge instead of scrolling on forever. */
const PAGE = 12

export function LibraryPage() {
  const { lessons, error } = useLessons()
  const [difficulty, setDifficulty] = useState<Difficulty | null>(null)
  const [theme, setTheme] = useState<string | null>(null)
  const [shownCount, setShownCount] = useState(PAGE)

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

  // A new filter is a new list; keeping the old page depth would show a
  // "Show more" button under three results.
  useEffect(() => setShownCount(PAGE), [difficulty, theme])

  const page = shown.slice(0, shownCount)
  const remaining = shown.length - page.length

  return (
    <div className="page wide">
      <AppHeader />

      <header className="page-head">
        <h1 className="page-title">Library</h1>
        <p className="muted">
          Real clips with bilingual subtitles. Tap any word to look it up.
        </p>
      </header>

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
      {!lessons && !error && (
        <div className="grid" aria-hidden="true">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="lesson-card skeleton">
              <div className="thumb" />
              <div className="lesson-card-body">
                <div className="skeleton-line" />
                <div className="skeleton-line short" />
              </div>
            </div>
          ))}
        </div>
      )}
      {lessons && shown.length === 0 && (
        <div className="empty-state">
          <h2 className="empty-title">Nothing at this level yet</h2>
          <p className="muted">Try another filter — the library is still growing.</p>
        </div>
      )}

      <div className="grid">
        {page.map((lesson) => (
          <LessonCard key={lesson.id} lesson={lesson} />
        ))}
      </div>

      {remaining > 0 && (
        <div className="more-row">
          <button className="btn-quiet" onClick={() => setShownCount((n) => n + PAGE)}>
            Show more
          </button>
          <span className="muted small">
            {page.length} of {shown.length}
          </span>
        </div>
      )}
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
