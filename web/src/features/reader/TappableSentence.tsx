// Renders an English sentence with individually tappable word tokens, using the
// precomputed char_span offsets from the LessonPackage (arch §4.2). Text
// between/around tokens (spaces, punctuation) renders as plain, non-tappable
// spans so nothing is lost.
import type { ReactNode } from 'react'
import type { Sentence, TokenSpan } from '../../lib/api'

export function TappableSentence({
  sentence,
  onWordTap,
  className = 'subtitle-en',
}: {
  sentence: Sentence
  onWordTap: (token: TokenSpan) => void
  /** The same markup serves the big active caption and the transcript rows. */
  className?: string
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
    parts.push(
      <button
        key={`tok-${i}`}
        type="button"
        className="token"
        onClick={() => onWordTap(tok)}
      >
        {text.slice(start, end)}
      </button>,
    )
    cursor = end
  })
  if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>)

  return <p className={className}>{parts}</p>
}
