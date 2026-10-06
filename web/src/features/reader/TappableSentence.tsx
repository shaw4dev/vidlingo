// Renders an English sentence with individually tappable word tokens, using the
// precomputed char_span offsets from the LessonPackage (arch §4.2). Text
// between/around tokens (spaces, punctuation) renders as plain, non-tappable
// spans so nothing is lost.
//
// Tokens carry their saved-word status as a class. A word list is only worth
// keeping if it shows up where the words are: seeing a word you saved from
// Friends turn up underlined in a TED talk is the moment the list stops being
// a list. Nothing is tinted for a signed-out visitor — there is no list yet,
// and colouring at random would be a lie about progress.
import type { ReactNode } from 'react'
import type { Sentence, TokenSpan } from '../../lib/api'
import type { WordStatus } from '../vocab/useVocabIndex'

const WORD_STATUS_TITLES: Record<WordStatus, string> = {
  new: 'Saved — not reviewed yet',
  learning: 'Saved — still learning',
  mastered: 'Saved — mastered',
}

export function TappableSentence({
  sentence,
  onWordTap,
  className = 'subtitle-en',
  status,
}: {
  sentence: Sentence
  onWordTap: (token: TokenSpan) => void
  /** The same markup serves the big active caption and the transcript rows. */
  className?: string
  /** Lemma → status, from the signed-in user's vocab list. */
  status?: ReadonlyMap<string, WordStatus>
}) {
  const text = sentence.text_en
  const tokens = [...sentence.tokens].sort((a, b) => a.char_span[0] - b.char_span[0])

  const parts: ReactNode[] = []
  let cursor = 0
  tokens.forEach((tok, i) => {
    const [start, end] = tok.char_span
    if (start > cursor) {
      parts.push(<span key={`gap-${i}`}>{text.slice(cursor, start)}</span>)
    }
    const state = status?.get(tok.lemma.toLowerCase())
    parts.push(
      <button
        key={`tok-${i}`}
        type="button"
        className={state ? `token tok-${state}` : 'token'}
        title={state ? WORD_STATUS_TITLES[state] : undefined}
        onClick={(e) => {
          // A word tap is not a sentence tap. The transcript row this sits in
          // has its own onClick that jumps to the sentence and closes the open
          // word card; letting the click bubble meant tapping a word in the
          // transcript jumped there and then immediately dismissed the card it
          // had just opened, so the card only ever worked in the caption.
          e.stopPropagation()
          onWordTap(tok)
        }}
      >
        {text.slice(start, end)}
      </button>,
    )
    cursor = end
  })
  if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>)

  return <p className={className}>{parts}</p>
}
