// Her vocabulary list — the payoff for every "+ Add to vocab" tap.
//
// The backend already embeds each item's source sentence (T06), so a saved word
// keeps the scene it came from: the English line, its translation, and a link
// back into the Reader at that lesson. Without that a vocab list is just a
// word list, which is the thing flashcard apps already do badly.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { useReviewSummary } from '../features/review/useReviewSummary'
import { api, ApiError, type Mastery, type VocabItem } from '../lib/api'

// The order the filter chips appear in, weakest first. It used to double as a
// click-cycle for the pill; nothing cycles now, so the name says what is left.
const MASTERY_ORDER: Mastery[] = ['new', 'learning', 'mastered']
const MASTERY_LABELS: Record<Mastery, string> = {
  new: 'New',
  learning: 'Learning',
  mastered: 'Mastered',
}

export function VocabPage() {
  const review = useReviewSummary()
  const [items, setItems] = useState<VocabItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Mastery | null>(null)

  useEffect(() => {
    api
      .listVocab()
      .then(setItems)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load your vocab'),
      )
  }, [])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const it of items ?? []) c[it.mastery] = (c[it.mastery] ?? 0) + 1
    return c
  }, [items])

  const shown = useMemo(
    () => (items ?? []).filter((it) => filter == null || it.mastery === filter),
    [items, filter],
  )

  const remove = (item: VocabItem) => {
    const snapshot = items
    setItems((prev) => (prev ?? []).filter((it) => it.id !== item.id))
    api.deleteVocab(item.id).catch(() => {
      setItems(snapshot)
      setError('Could not remove that word')
    })
  }

  return (
    <div className="page">
      <AppHeader />

      <h2>My words</h2>

      {review && review.scheduled_today > 0 && (
        <Link className="review-banner" to="/review">
          今日安排 {review.scheduled_today} 个复习 →
        </Link>
      )}

      {items && items.length > 0 && (
        <div className="filters">
          <button
            className={filter == null ? 'filter-chip on' : 'filter-chip'}
            onClick={() => setFilter(null)}
          >
            All {items.length}
          </button>
          {MASTERY_ORDER.map((m) => (
            <button
              key={m}
              className={filter === m ? 'filter-chip on' : 'filter-chip'}
              onClick={() => setFilter(filter === m ? null : m)}
            >
              {MASTERY_LABELS[m]} {counts[m] ?? 0}
            </button>
          ))}
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {!items && !error && <p className="muted">Loading…</p>}

      {items && items.length === 0 && (
        <p className="muted">
          Nothing saved yet. Tap a word while watching and choose{' '}
          <strong>+ Add to vocab</strong> — it will land here with the sentence you
          met it in.
        </p>
      )}

      <ul className="vocab-list">
        {shown.map((item) => (
          <li key={item.id} className="card vocab-item">
            <div className="vocab-head">
              <Link to={`/word/${encodeURIComponent(item.lemma)}`} className="vocab-word">
                {item.lemma}
              </Link>
              {item.surface && item.surface.toLowerCase() !== item.lemma && (
                <span className="muted small"> · seen as “{item.surface}”</span>
              )}
              <span className="spacer" />
              {/* Read-only. This used to cycle new -> learning -> mastered on
                  click, which meant the label said whatever was last tapped.
                  It is now derived from the review schedule, so it moves
                  because the answers moved it. */}
              <span className={`mastery mastery-${item.mastery}`}>
                {MASTERY_LABELS[item.mastery as Mastery] ?? item.mastery}
              </span>
              <button className="icon-btn" aria-label="Remove" onClick={() => remove(item)}>
                ✕
              </button>
            </div>

            {item.source ? (
              <div className="vocab-source">
                <p className="vocab-source-en">{item.source.text_en}</p>
                <p className="vocab-source-zh muted small">{item.source.text_zh}</p>
                <Link
                  to={`/reader/${item.source.lesson_id}?s=${item.source.idx}`}
                  className="link"
                >
                  {item.source.lesson_title} →
                </Link>
              </div>
            ) : (
              <p className="muted small">Saved without a source sentence.</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
