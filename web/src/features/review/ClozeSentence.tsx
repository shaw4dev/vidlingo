// The sentence with the answer punched out of it.
//
// A sibling of TappableSentence rather than a mode of it: the span-splicing
// walk is the same, but everything around it differs — these are blanks, not
// tokens, they carry no tap handlers, and they change appearance on reveal.
// One component doing both would need a flag that helps neither caller.
import type { ReviewSource } from '../../lib/api'

export function ClozeSentence({
  source,
  revealed,
}: {
  source: ReviewSource
  revealed: boolean
}) {
  const text = source.text_en
  const spans = [...source.blank_spans].sort((a, b) => a[0] - b[0])

  const parts: React.ReactNode[] = []
  let cursor = 0
  spans.forEach(([start, end], i) => {
    if (start > cursor) parts.push(text.slice(cursor, start))
    const word = text.slice(start, end)
    parts.push(
      <span key={`b${i}`} className={revealed ? 'cloze-revealed' : 'cloze-blank'}>
        {/* The blank is sized from the word it hides, so the gap does not give
            away a three-letter answer by looking like a ten-letter one. */}
        {revealed ? word : ' '.repeat(Math.max(3, word.length))}
      </span>,
    )
    cursor = end
  })
  if (cursor < text.length) parts.push(text.slice(cursor))

  return <p className="cloze-line">{parts}</p>
}
