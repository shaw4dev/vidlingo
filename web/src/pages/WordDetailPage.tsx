// Word detail (Feature B): tap a word anywhere -> see its meaning (the T13 word
// card) and the fragments that contain it. Backed by GET /words/{lemma}/
// occurrences, which also kicks off a background backfill when coverage is
// thin, so an under-covered word gains more fragments on a later visit.
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type OccurrencesResponse } from '../lib/api'
import { AppHeader } from '../components/AppHeader'
import { WordCard } from '../features/word/WordCard'

export function WordDetailPage() {
  const { word } = useParams<{ word: string }>()
  const [data, setData] = useState<OccurrencesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pos, setPos] = useState(0)

  useEffect(() => {
    if (!word) return
    setData(null)
    setPos(0)
    api
      .wordOccurrences(word)
      .then(setData)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load word'),
      )
  }, [word])

  return (
    <div className="page word-page">
      <AppHeader />
      <div className="reader-bar">
        <button className="neighbour" onClick={() => history.back()}>
          ◀ Back
        </button>
        <div className="reader-title">
          <div className="lesson-title">{data?.lemma ?? word}</div>
        </div>
        <span className="neighbour disabled" />
      </div>

      {word && (
        <WordCard
          key={word}
          surface={word}
          lemma={data?.lemma ?? word}
          // We're already on the word's own page — no need to link back to it.
          showMoreVideos={false}
        />
      )}

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted center">Loading…</p>}

      {data && data.count === 0 && (
        <p className="muted center">
          No fragments yet for “{data.lemma}”. We're looking for some — check back soon.
        </p>
      )}

      {data && data.count > 0 && (
        <main className="word-detail">
          <div className="muted small">
            {pos + 1} / {data.count} fragment{data.count > 1 ? 's' : ''}
          </div>

          <Fragment occ={data.occurrences[pos]} />

          <div className="controls">
            <button onClick={() => setPos((p) => Math.max(0, p - 1))} disabled={pos === 0}>
              ◀ Prev
            </button>
            <button
              onClick={() => setPos((p) => Math.min(data.count - 1, p + 1))}
              disabled={pos === data.count - 1}
            >
              Next ▶
            </button>
          </div>
        </main>
      )}
    </div>
  )
}

function Fragment({ occ }: { occ: OccurrencesResponse['occurrences'][number] }) {
  return (
    <div className="card fragment">
      <p className="fragment-en">{occ.text_en}</p>
      <p className="fragment-zh muted">{occ.text_zh}</p>
      <div className="fragment-foot">
        <span className="muted small">{occ.lesson_title}</span>
        {/* `?s=` drops her at the sentence, not at the top of a 2-minute clip. */}
        <Link to={`/reader/${occ.lesson_id}?s=${occ.idx}`} className="link">
          Watch in context →
        </Link>
      </div>
    </div>
  )
}
