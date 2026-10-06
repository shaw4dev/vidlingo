// The library: everything in the corpus as one filterable grid.
//
// Explore is the shop window — shelves, a hero, an editorial order. This is
// the back of the shop: no curation, every clip, and filters that answer
// "show me only the two-minute hard ones". Both exist because browsing and
// searching are different jobs, and a page that tries to be both is a grid
// with a banner on it.
//
// The filters read from the URL, so a shelf's "See all" link can land here
// already narrowed, and so a narrowed view is a link she can send someone.
import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { LessonCard } from '../features/library/LessonCard'
import { showOf, showsByCatalogue } from '../features/library/shows'
import {
  DIFFICULTY_LABELS,
  levelsPresent,
  useLessons,
  type Difficulty,
} from '../features/library/useLessons'

/** How many cards to render before "Show more". A screenful and a bit, so the
 *  page has a visible bottom edge instead of scrolling on forever. */
const PAGE = 12

export function LibraryPage() {
  const { lessons, error } = useLessons()
  const [params, setParams] = useSearchParams()

  const level = (params.get('level') as Difficulty | null) ?? null
  const show = params.get('show')
  // Page depth lives in the URL too, so Back out of a lesson returns to the
  // same scroll depth instead of the first twelve cards.
  const shownCount = Number.parseInt(params.get('n') ?? '', 10) || PAGE

  const shows = useMemo(() => showsByCatalogue(lessons ?? []), [lessons])
  // Only the levels the corpus actually has: a chip that can only ever say
  // "nothing matches" looks like a bug in the filter.
  const levels = useMemo(() => levelsPresent(lessons ?? []), [lessons])

  const shown = useMemo(
    () =>
      (lessons ?? []).filter(
        (l) =>
          (level == null || l.difficulty === level) &&
          (show == null || showOf(l).key === show),
      ),
    [lessons, level, show],
  )

  // A new filter is a new list; keeping the old page depth would show a
  // "Show more" button under three results.
  useEffect(() => {
    if (params.get('n')) {
      const next = new URLSearchParams(params)
      next.delete('n')
      setParams(next, { replace: true })
    }
    // Only when the *filters* change — not when n itself does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, show])

  function setFilter(key: 'level' | 'show', value: string | null) {
    const next = new URLSearchParams(params)
    if (value == null) next.delete(key)
    else next.set(key, value)
    next.delete('n')
    setParams(next)
  }

  const page = shown.slice(0, shownCount)
  const remaining = shown.length - page.length

  return (
    <div className="page wide">
      <AppHeader />

      <header className="page-head">
        <h1 className="page-title">Library</h1>
        <p className="muted">
          {lessons ? `${lessons.length} clips` : 'Everything'} with bilingual subtitles. Tap any
          word to look it up.
        </p>
      </header>

      <div className="filters">
        <Chip active={level == null} onClick={() => setFilter('level', null)}>
          All levels
        </Chip>
        {levels.map((d) => (
          <Chip key={d} active={level === d} onClick={() => setFilter('level', d)}>
            {DIFFICULTY_LABELS[d]}
          </Chip>
        ))}
        {shows.length > 1 && <span className="filter-sep" />}
        {shows.length > 1 && (
          <Chip active={show == null} onClick={() => setFilter('show', null)}>
            All shows
          </Chip>
        )}
        {shows.length > 1 &&
          shows.map(({ show: s, lessons: clips }) => (
            <Chip
              key={s.key}
              active={show === s.key}
              onClick={() => setFilter('show', show === s.key ? null : s.key)}
            >
              {s.label}
              <span className="chip-count">{clips.length}</span>
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
          <h2 className="empty-title">Nothing matches those filters</h2>
          <p className="muted">Drop one of them — the library is still growing.</p>
        </div>
      )}

      <div className="grid">
        {page.map((lesson) => (
          <LessonCard key={lesson.id} lesson={lesson} />
        ))}
      </div>

      {remaining > 0 && (
        <div className="more-row">
          <button
            className="btn-quiet"
            onClick={() => {
              const next = new URLSearchParams(params)
              next.set('n', String(shownCount + PAGE))
              setParams(next, { replace: true })
            }}
          >
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
