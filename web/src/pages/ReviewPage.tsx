// Today's review session — the thing that makes a saved word come back.
//
// Front: the line the word was met in, with the word punched out. Nothing
// else, because a card that tests two abilities at once cannot say which one
// failed. Back: the answer in place, the pronunciation, the meaning, and the
// clip. Then one of three buttons, which is what moves the schedule.
//
// The clip is still the point — it is what makes this something other than a
// flashcard app — but it belongs to the feedback, not to the question. Its
// audio contains the answer, and a learner who knows a word without being able
// to catch it at speed should not be recorded as having forgotten it.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AppHeader } from '../components/AppHeader'
import { ClipPlayer } from '../features/review/ClipPlayer'
import { ClozeSentence } from '../features/review/ClozeSentence'
import { useReviewQueue } from '../features/review/useReviewQueue'
import { bumpReviewSummary } from '../features/review/useReviewSummary'
import { useDefinition } from '../features/word/useDefinition'
import type { Grade, ReviewCard } from '../lib/api'

const GRADES: { grade: Grade; label: string; hint: string; className: string }[] = [
  { grade: 'forgot', label: '忘了', hint: '1', className: 'grade-btn grade-forgot' },
  { grade: 'vague', label: '模糊', hint: '2', className: 'grade-btn grade-vague' },
  { grade: 'remembered', label: '记得', hint: '3', className: 'grade-btn grade-remembered' },
]

export function ReviewPage() {
  const session = useReviewQueue()
  const { cards, error, index, current, grade } = session
  const [revealed, setRevealed] = useState(false)

  // Started when the front appears, read when a button is pressed. Hesitating
  // before "记得" is not the same answer as pressing it instantly, and the
  // difference is a training signal worth capturing while it is free.
  const shownAt = useRef<number>(Date.now())
  useEffect(() => {
    setRevealed(false)
    shownAt.current = Date.now()
  }, [current?.vocab_item_id])

  const answer = useCallback(
    (g: Grade) => {
      if (!current) return
      grade(current, g, Date.now() - shownAt.current)
      bumpReviewSummary()
    },
    [current, grade],
  )

  // Space reveals, 1/2/3 grade. The Reader already establishes keyboard
  // control, and a review session is the screen where reaching for the mouse
  // between every card is most obviously wrong.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!current) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setRevealed(true)
        return
      }
      if (!revealed) return
      const at = ['1', '2', '3'].indexOf(e.key)
      if (at !== -1) answer(GRADES[at].grade)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current, revealed, answer])

  return (
    <div className="page">
      <AppHeader />
      <div className="page-head">
        <h2 className="page-title">Review</h2>
        {cards && cards.length > 0 && (
          <span className="muted small">
            {Math.min(index + 1, cards.length)} / {cards.length}
          </span>
        )}
      </div>

      {error && <p className="error">{error}</p>}
      {!cards && !error && <p className="muted">Loading…</p>}

      {cards && cards.length === 0 && <NothingDue session={session} />}
      {cards && cards.length > 0 && !current && <Finished session={session} />}

      {current && (
        <>
          <Card card={current} revealed={revealed} />
          {!revealed ? (
            <button type="button" className="btn-small" onClick={() => setRevealed(true)}>
              显示答案 <span className="muted small">(Space)</span>
            </button>
          ) : (
            <div className="grade-row">
              {GRADES.map((g) => (
                <button
                  key={g.grade}
                  type="button"
                  className={g.className}
                  onClick={() => answer(g.grade)}
                >
                  {g.label}
                  <span className="grade-hint">{g.hint}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function Card({ card, revealed }: { card: ReviewCard; revealed: boolean }) {
  // Fetched only once the answer is showing: the senses are the back of the
  // card, and asking for them up front would spend a request on every card the
  // user gets right without needing them.
  const { definition } = useDefinition(revealed ? card.lemma : null)
  const src = card.source

  return (
    <div className="card review-card">
      {/* Playing belongs to the *back*. The audio contains the blanked word --
          only sentence-level timestamps exist, so there is no way to bleep it
          -- which would make "play the line" the answer delivered through
          another channel. Worse, someone who knows the word but cannot catch
          it at speed would press 忘了, and the scheduler would record a
          listening gap as a vocabulary one, mislabelling the very data
          review_log exists to collect.

          The picture is a different matter and stays visible throughout: a
          paused frame of the scene is a fair cue and gives nothing away. */}
      {src && (
        <ClipPlayer
          youtubeId={src.youtube_id}
          startMs={src.start_ms}
          endMs={src.end_ms}
          cardKey={card.vocab_item_id}
          revealed={revealed}
        />
      )}

      {card.card_kind === 'cloze' && src && (
        <>
          <ClozeSentence source={src} revealed={revealed} />
          {/* The line that makes the blank answerable. Without it a cloze over
              conversational English is under-determined -- "I ___ you" admits
              love, told, owe, miss -- so someone who knows the word perfectly
              still cannot answer, and the 忘了 they press is noise in the
              schedule. Other vocabulary apps prompt with a dictionary gloss;
              the sentence translation is better, because it pins down which
              sense of the word this scene used. */}
          <p className="cloze-zh">{src.text_zh}</p>
        </>
      )}

      {/* No usable blank, so the English line *is* the answer and must stay
          hidden until the reveal. Prompting from the translation keeps the
          clip and the zh -> en direction: a harder card, not a broken one. */}
      {card.card_kind === 'zh_prompt' && src && (
        <p className="cloze-line">{revealed ? src.text_en : src.text_zh}</p>
      )}

      {card.card_kind === 'bare' && (
        <p className="cloze-line">
          {revealed ? card.lemma : <span className="muted">还记得这个词的意思吗?</span>}
        </p>
      )}

      {/* Said out loud, because a learner may well remember meeting this word
          somewhere else entirely, and an unexplained strange sentence reads as
          a bug rather than a substitution. */}
      {src?.borrowed && <p className="cloze-note">例句来自另一个视频</p>}

      {revealed && (
        <div className="review-back">
          <div className="review-answer">
            <strong>{card.lemma}</strong>
            {(definition?.phonetic ?? card.definition?.phonetic) && (
              <span className="muted small"> {definition?.phonetic ?? card.definition?.phonetic}</span>
            )}
          </div>
          {(definition?.gloss_zh ?? card.definition?.gloss_zh) && (
            <p className="review-gloss">{definition?.gloss_zh ?? card.definition?.gloss_zh}</p>
          )}
          {definition?.senses?.[0] && (
            <p className="muted small">{definition.senses[0].definition}</p>
          )}
          {src && (
            <Link className="link small" to={`/reader/${src.lesson_id}?s=${src.idx}`}>
              在 Reader 里看这一句 →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

function NothingDue({ session }: { session: ReturnType<typeof useReviewQueue> }) {
  return (
    <div className="review-empty">
      <p>今天没有要复习的词。</p>
      {session.dueTotal > 0 ? (
        <p className="muted small">
          今天的 {session.cap} 个已经做完了,还有 {session.dueTotal} 个排在后面。
        </p>
      ) : (
        <p className="muted small">
          在 <Link className="link" to="/">
            Library
          </Link>{' '}
          里点任意一个词加进生词本,它明天就会出现在这里。
        </p>
      )}
    </div>
  )
}

function Finished({ session }: { session: ReturnType<typeof useReviewQueue> }) {
  const left = Math.max(0, session.dueTotal - session.done)
  return (
    <div className="review-empty">
      <p>今日复习完成 ✓</p>
      {left > 0 && <p className="muted small">还有 {left} 个将在接下来几天安排。</p>}
      <Link className="link" to="/vocab">
        看看我的生词本 →
      </Link>
    </div>
  )
}
