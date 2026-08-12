// The word card (T13): what she sees the moment she taps an unknown word.
//
// Phonetic + 🔊, part of speech, English senses, a Chinese gloss when the
// backend has one, and the in-context meaning — which is just the source
// sentence's own translation, already in the LessonPackage. Two actions:
// save it to vocab (T06), and jump to other real videos using it (T05/T18).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../lib/api'
import { pronounce } from '../../lib/tts'
import { useDefinition } from './useDefinition'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

export function WordCard({
  surface,
  lemma,
  sentenceId,
  contextZh,
  showMoreVideos = true,
  onClose,
}: {
  /** The word exactly as it appeared, e.g. "running". */
  surface: string
  /** Its dictionary form, e.g. "run" — what we look up and save. */
  lemma: string
  /** Source sentence, so a saved word can link back to where she met it. */
  sentenceId?: string
  /** The sentence's Chinese translation — the in-context meaning. */
  contextZh?: string
  showMoreVideos?: boolean
  onClose?: () => void
}) {
  const { definition, loading, error } = useDefinition(lemma)
  const [save, setSave] = useState<SaveState>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const addToVocab = () => {
    setSave('saving')
    setSaveError(null)
    api
      .addVocab({ lemma, surface, source_sentence_id: sentenceId })
      .then(() => setSave('saved'))
      .catch((err) => {
        // Already in her list is a success from her point of view, not an error.
        if (err instanceof ApiError && err.status === 409) {
          setSave('saved')
          return
        }
        setSave('error')
        setSaveError(err instanceof ApiError ? err.message : 'Could not save')
      })
  }

  return (
    <section className="card word-card">
      <header className="word-card-head">
        <div>
          <strong className="word-card-word">{surface}</strong>
          {lemma !== surface.toLowerCase() && (
            <span className="muted small"> · {lemma}</span>
          )}
          {definition?.phonetic && (
            <span className="muted small phonetic"> {definition.phonetic}</span>
          )}
        </div>
        <button
          className="icon-btn"
          title="Pronounce"
          aria-label={`Pronounce ${surface}`}
          onClick={() => pronounce(lemma, definition?.audio_url)}
        >
          🔊
        </button>
        {onClose && (
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        )}
      </header>

      {loading && <p className="muted small">Looking it up…</p>}
      {error && <p className="error small">{error}</p>}

      {definition?.gloss_zh && <p className="word-gloss">{definition.gloss_zh}</p>}

      {definition && definition.senses.length > 0 && (
        <ol className="senses">
          {definition.senses.map((sense, i) => (
            <li key={i}>
              {sense.pos && <span className="pos">{sense.pos}</span>}
              <span>{sense.definition}</span>
              {sense.example && <em className="muted small example">“{sense.example}”</em>}
            </li>
          ))}
        </ol>
      )}

      {!loading && !error && !definition && (
        <p className="muted small">
          No dictionary entry for “{lemma}”. You can still save it and see it in other videos.
        </p>
      )}

      {contextZh && (
        <p className="word-context">
          <span className="muted small">In this sentence: </span>
          {contextZh}
        </p>
      )}

      <div className="word-card-actions">
        <button onClick={addToVocab} disabled={save === 'saving' || save === 'saved'}>
          {save === 'saved' ? '✓ In your vocab' : save === 'saving' ? 'Saving…' : '+ Add to vocab'}
        </button>
        {showMoreVideos && (
          <Link className="link" to={`/word/${encodeURIComponent(lemma)}`}>
            More videos with this word →
          </Link>
        )}
      </div>
      {saveError && <p className="error small">{saveError}</p>}
    </section>
  )
}
