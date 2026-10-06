// The strip above the transcript that explains the colours — and, for a
// visitor, argues for the account that would produce them.
//
// It counts *this* transcript, not the whole list. "4 of your words are in
// this clip" is a fact about the thing on screen; "you have 214 saved words"
// is a fact about an account page, and belongs on one.
import { useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import type { Sentence } from '../../lib/api'
import type { WordStatus } from '../vocab/useVocabIndex'

/** Same order and same wording as the vocab page's filter chips. */
const STATES: { key: WordStatus; label: string }[] = [
  { key: 'new', label: 'new' },
  { key: 'learning', label: 'learning' },
  { key: 'mastered', label: 'mastered' },
]

export function WordStatusLegend({
  sentences,
  status,
  signedIn,
}: {
  sentences: Sentence[]
  status: ReadonlyMap<string, WordStatus>
  signedIn: boolean
}) {
  const location = useLocation()

  const counts = useMemo(() => {
    // Distinct lemmas, not occurrences: "mean" said nine times is one word she
    // is learning, and counting it nine times would flatter the number.
    const seen = new Map<WordStatus, Set<string>>()
    for (const s of sentences) {
      for (const t of s.tokens) {
        const lemma = t.lemma.toLowerCase()
        const state = status.get(lemma)
        if (!state) continue
        const bucket = seen.get(state) ?? new Set<string>()
        bucket.add(lemma)
        seen.set(state, bucket)
      }
    }
    return seen
  }, [sentences, status])

  if (!signedIn) {
    return (
      <div className="legend legend-pitch">
        <span className="muted small">
          Tap any word for its meaning. Save one and it lights up here — and in every other clip
          that uses it.
        </span>
        <Link
          className="link"
          to="/login"
          state={{ from: location.pathname + location.search, mode: 'register' }}
        >
          Sign up free →
        </Link>
      </div>
    )
  }

  const present = STATES.filter(({ key }) => (counts.get(key)?.size ?? 0) > 0)

  if (present.length === 0) {
    return (
      <div className="legend">
        <span className="muted small">
          None of your saved words appear in this clip yet. Tap one to add it.
        </span>
      </div>
    )
  }

  return (
    <div className="legend">
      {present.map(({ key, label }) => (
        <span className="legend-item" key={key}>
          <span className={`swatch swatch-${key}`} aria-hidden="true" />
          {counts.get(key)!.size} {label}
        </span>
      ))}
      <span className="spacer" />
      <Link className="link small" to="/vocab">
        Your words →
      </Link>
    </div>
  )
}
