// The Reader (T12): YouTube IFrame player driven by sentence timestamps, with
// sentence-by-sentence stepping, single-sentence loop, speed control, and
// tappable bilingual subtitles (four display modes). Tapping a word opens the
// word card (T13): meaning, pronunciation, add-to-vocab, and reverse lookup.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type LessonDetail, type Sentence, type TokenSpan } from '../lib/api'
import { useYouTubePlayer } from '../features/reader/useYouTubePlayer'
import { TappableSentence } from '../features/reader/TappableSentence'
import { WordCard } from '../features/word/WordCard'

type SubtitleMode = 'bi' | 'en' | 'zh' | 'off'

const MODE_LABELS: Record<SubtitleMode, string> = {
  bi: '中英',
  en: '仅英',
  zh: '仅中',
  off: '关闭',
}

const RATES = [0.5, 0.75, 1, 1.25, 1.5]

function indexAtMs(sentences: Sentence[], ms: number): number {
  for (let i = 0; i < sentences.length; i++) {
    if (ms >= sentences[i].start_ms && ms < sentences[i].end_ms) return i
  }
  return -1
}

export function ReaderPage() {
  const { lessonId } = useParams<{ lessonId: string }>()
  const [lesson, setLesson] = useState<LessonDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!lessonId) return
    setLesson(null)
    api
      .getLesson(lessonId)
      .then(setLesson)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load lesson'),
      )
  }, [lessonId])

  if (error) {
    return (
      <div className="page">
        <header className="topbar">
          <Link to="/" className="link">
            ← Lessons
          </Link>
        </header>
        <p className="error">{error}</p>
      </div>
    )
  }
  if (!lesson) {
    return (
      <div className="page">
        <header className="topbar">
          <Link to="/" className="link">
            ← Lessons
          </Link>
        </header>
        <p className="muted">Loading…</p>
      </div>
    )
  }
  return <Reader lesson={lesson} />
}

function Reader({ lesson }: { lesson: LessonDetail }) {
  const sentences = lesson.sentences
  const { wrapRef, ready, playing, currentMs, controls, setRate } = useYouTubePlayer(
    lesson.youtube_id,
  )

  const [activeIdx, setActiveIdx] = useState(0)
  const [repeat, setRepeat] = useState(false)
  const [autoPause, setAutoPause] = useState(true)
  const [rate, setRateState] = useState(1)
  const [mode, setMode] = useState<SubtitleMode>('bi')
  const [selected, setSelected] = useState<TokenSpan | null>(null)

  const active = sentences[activeIdx]

  // Boundary handling: loop, auto-pause, or follow the playhead.
  const pausedAtEnd = useRef(false)
  useEffect(() => {
    if (!ready || !active) return
    if (repeat) {
      if (currentMs >= active.end_ms || currentMs < active.start_ms - 250) {
        controls.seekMs(active.start_ms)
      }
      return
    }
    if (autoPause) {
      if (playing && currentMs >= active.end_ms && !pausedAtEnd.current) {
        pausedAtEnd.current = true
        controls.pause()
      }
      return
    }
    // Follow mode: keep the highlight on whatever sentence is playing.
    const idx = indexAtMs(sentences, currentMs)
    if (idx !== -1 && idx !== activeIdx) setActiveIdx(idx)
  }, [currentMs, ready, playing, repeat, autoPause, active, activeIdx, sentences, controls])

  // Reset the auto-pause latch whenever we (re)enter the active sentence.
  useEffect(() => {
    if (active && currentMs < active.end_ms) pausedAtEnd.current = false
  }, [currentMs, active])

  const goTo = useCallback(
    (idx: number) => {
      const clamped = Math.max(0, Math.min(sentences.length - 1, idx))
      setActiveIdx(clamped)
      setSelected(null) // the card belongs to the sentence we're leaving
      pausedAtEnd.current = false
      controls.seekMs(sentences[clamped].start_ms)
      controls.play()
    },
    [sentences, controls],
  )

  const togglePlay = useCallback(() => {
    if (playing) {
      controls.pause()
      return
    }
    // If we're outside the active sentence (e.g. auto-paused at its end),
    // replay it from the start; otherwise resume in place.
    if (currentMs < active.start_ms || currentMs >= active.end_ms) {
      pausedAtEnd.current = false
      controls.seekMs(active.start_ms)
    }
    controls.play()
  }, [playing, currentMs, active, controls])

  const changeRate = useCallback(
    (r: number) => {
      setRateState(r)
      setRate(r)
    },
    [setRate],
  )

  const showEn = mode === 'bi' || mode === 'en'
  const showZh = mode === 'bi' || mode === 'zh'

  return (
    <div className="page reader">
      <header className="topbar">
        <Link to="/" className="link">
          ← Lessons
        </Link>
        <span className="spacer" />
        <span className="muted small">{lesson.title}</span>
      </header>

      {lesson.youtube_id ? (
        <div className="player-wrap" ref={wrapRef} />
      ) : (
        <p className="error">This lesson has no YouTube video.</p>
      )}

      {/* Caption area for the active sentence */}
      <div className="caption">
        {mode === 'off' ? (
          <p className="muted small">Subtitles off</p>
        ) : (
          <>
            {showEn && <TappableSentence sentence={active} onWordTap={setSelected} />}
            {showZh && <p className="subtitle-zh">{active.text_zh}</p>}
          </>
        )}
        {selected && (
          <WordCard
            key={`${active.id}:${selected.char_span[0]}`}
            surface={selected.surface}
            lemma={selected.lemma}
            sentenceId={active.id}
            contextZh={active.text_zh}
            onClose={() => setSelected(null)}
          />
        )}
      </div>

      {/* Playback controls */}
      <div className="controls">
        <button onClick={() => goTo(activeIdx - 1)} disabled={activeIdx === 0}>
          ◀ Prev
        </button>
        <button onClick={togglePlay} disabled={!ready}>
          {playing ? '❚❚ Pause' : '▶ Play'}
        </button>
        <button
          onClick={() => goTo(activeIdx + 1)}
          disabled={activeIdx === sentences.length - 1}
        >
          Next ▶
        </button>
        <button
          className={repeat ? 'toggle on' : 'toggle'}
          onClick={() => setRepeat((v) => !v)}
          title="Loop the current sentence"
        >
          ↻ Repeat
        </button>
        <button
          className={autoPause ? 'toggle on' : 'toggle'}
          onClick={() => setAutoPause((v) => !v)}
          title="Pause at the end of each sentence"
        >
          ⏸ Auto-pause
        </button>
      </div>

      <div className="controls">
        <span className="muted small">Speed</span>
        {RATES.map((r) => (
          <button
            key={r}
            className={rate === r ? 'toggle on' : 'toggle'}
            onClick={() => changeRate(r)}
          >
            {r}×
          </button>
        ))}
        <span className="spacer" />
        <span className="muted small">Subtitles</span>
        {(Object.keys(MODE_LABELS) as SubtitleMode[]).map((m) => (
          <button
            key={m}
            className={mode === m ? 'toggle on' : 'toggle'}
            onClick={() => setMode(m)}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      {/* Full transcript — click any sentence to jump */}
      <ol className="transcript">
        {sentences.map((s, i) => (
          <li
            key={s.id}
            className={i === activeIdx ? 'sentence-row active' : 'sentence-row'}
            onClick={() => goTo(i)}
          >
            <span className="sentence-en">{s.text_en}</span>
            {showZh && <span className="sentence-zh muted small">{s.text_zh}</span>}
          </li>
        ))}
      </ol>
    </div>
  )
}
