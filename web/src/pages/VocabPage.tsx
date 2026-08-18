// Her vocabulary list — the payoff for every "+ Add to vocab" tap.
//
// The backend already embeds each item's source sentence (T06), so a saved word
// keeps the scene it came from: the English line, its translation, and a link
// back into the Reader at that lesson. Without that a vocab list is just a
// word list, which is the thing flashcard apps already do badly.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { api, ApiError, type Mastery, type VocabItem } from '../lib/api'

const MASTERY_CYCLE: Mastery[] = ['new', 'learning', 'mastered']
const MASTERY_LABELS: Record<Mastery, string> = {
  new: 'New',
  learning: 'Learning',
  mastered: 'Mastered',
}

export function VocabPage() {
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

  // Optimistic: the row updates immediately and rolls back if the API refuses.
  const cycleMastery = (item: VocabItem) => {
    const at = MASTERY_CYCLE.indexOf(item.mastery as Mastery)
    const next = MASTERY_CYCLE[(at + 1) % MASTERY_CYCLE.length]
    const before = item.mastery
    setItems((prev) =>
      (prev ?? []).map((it) => (it.id === item.id ? { ...it, mastery: next } : it)),
    )
    api.updateVocab(item.id, { mastery: next }).catch(() => {
      setItems((prev) =>
        (prev ?? []).map((it) => (it.id === item.id ? { ...it, mastery: before } : it)),
      )
      setError('Could not save that change')
    })
  }

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

      {items && items.length > 0 && (
        <div className="filters">
          <button
            className={filter == null ? 'filter-chip on' : 'filter-chip'}
            onClick={() => setFilter(null)}
          >
            All {items.length}
          </button>
          {MASTERY_CYCLE.map((m) => (
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
              <button
                className={`mastery mastery-${item.mastery}`}
                onClick={() => cycleMastery(item)}
                title="Click to change"
              >
                {MASTERY_LABELS[item.mastery as Mastery] ?? item.mastery}
              </button>
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
