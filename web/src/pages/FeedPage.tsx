// Shorts (Feature A): a vertical stream of 30-90s clip windows, one per screen.
//
// The first version put the window's whole transcript under the video as one
// paragraph — ninety seconds of speech run together, no translation, nothing
// tracking the audio. It read as a text dump with a video above it. A clip is
// watched, not read: so the caption is one line at a time, in step with the
// player, with its Chinese underneath, the way subtitles work everywhere else
// the learner has ever watched anything. The whole transcript is still one tap
// away, in the full lesson.
//
// Each item is a stage: the clip's own still, blurred, fills the screen behind
// the player, so every clip arrives in its own colour instead of on the same
// black page. Only the visible item mounts a player; the rest are posters.
//
// Mandatory snap plus an item taller than the viewport is a trap — the scroll
// gesture that should reveal more instead flings you to the next clip — so an
// item is exactly one viewport and nothing inside it scrolls.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type FeedClip, type TokenSpan } from '../lib/api'
import { AppHeader } from '../components/AppHeader'
import { useAuth } from '../auth/AuthContext'
import { clipTitle, showOf } from '../features/library/shows'
import { DIFFICULTY_LABELS, formatDuration, type Difficulty } from '../features/library/useLessons'
import { TappableSentence } from '../features/reader/TappableSentence'
import { useYouTubePlayer } from '../features/reader/useYouTubePlayer'
import { useVocabIndex, type WordStatus } from '../features/vocab/useVocabIndex'
import { WordCard } from '../features/word/WordCard'

const PAGE = 10

export function FeedPage() {
  const [clips, setClips] = useState<FeedClip[]>([])
  const [nextOffset, setNextOffset] = useState<number | null>(0)
  const [error, setError] = useState<string | null>(null)
  const [activeIdx, setActiveIdx] = useState(0)
  const loadingRef = useRef(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const { user } = useAuth()
  const { status } = useVocabIndex(!!user)

  const loadMore = useCallback(() => {
    if (loadingRef.current || nextOffset == null) return
    loadingRef.current = true
    api
      .getFeed({ limit: PAGE, offset: nextOffset })
      .then((res) => {
        setClips((prev) => [...prev, ...res.clips])
        setNextOffset(res.next_offset)
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load feed'),
      )
      .finally(() => {
        loadingRef.current = false
      })
  }, [nextOffset])

  // First page.
  useEffect(() => {
    loadMore()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Prefetch the next page as we approach the end.
  useEffect(() => {
    if (clips.length && activeIdx >= clips.length - 3) loadMore()
  }, [activeIdx, clips.length, loadMore])

  const goTo = useCallback((i: number) => {
    const el = scrollRef.current?.children[i] as HTMLElement | undefined
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  // ↑/↓ step between clips, the way a trackpad swipe does.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        goTo(Math.max(0, Math.min(clips.length - 1, activeIdx + (e.key === 'ArrowDown' ? 1 : -1))))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeIdx, clips.length, goTo])

  return (
    <div className="page feed-page">
      <AppHeader />
      {error ? (
        <p className="error feed-status">{error}</p>
      ) : clips.length === 0 ? (
        <p className="muted feed-status">Loading…</p>
      ) : (
        <div className="feed-scroll" ref={scrollRef}>
          {clips.map((clip, i) => (
            <FeedItem
              key={clip.clip_id}
              clip={clip}
              active={i === activeIdx}
              status={status}
              onVisible={() => setActiveIdx(i)}
              onPrev={i > 0 ? () => goTo(i - 1) : undefined}
              onNext={i < clips.length - 1 ? () => goTo(i + 1) : undefined}
            />
          ))}
          {nextOffset == null && (
            <p className="muted center small feed-end">You're all caught up.</p>
          )}
        </div>
      )}
    </div>
  )
}

function stillOf(clip: FeedClip): string | undefined {
  return clip.youtube_id ? `https://i.ytimg.com/vi/${clip.youtube_id}/hqdefault.jpg` : undefined
}

function FeedItem({
  clip,
  active,
  status,
  onVisible,
  onPrev,
  onNext,
}: {
  clip: FeedClip
  active: boolean
  status?: ReadonlyMap<string, WordStatus>
  onVisible: () => void
  onPrev?: () => void
  onNext?: () => void
}) {
  const ref = useRef<HTMLElement>(null)

  // Mark this item active when it fills most of the viewport.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && entry.intersectionRatio > 0.6) onVisible()
      },
      { threshold: [0.6] },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [onVisible])

  const still = stillOf(clip)
  const show = showOf(clip)
  const difficulty = clip.difficulty as Difficulty

  return (
    <section className="feed-item" ref={ref}>
      {still && (
        <div className="feed-backdrop" style={{ backgroundImage: `url(${still})` }} aria-hidden="true" />
      )}

      <div className="feed-stage">
        {active && clip.youtube_id ? (
          <ActiveClip clip={clip} status={status} />
        ) : (
          <>
            <div className="feed-video">
              <div className="clip-poster" style={still ? { backgroundImage: `url(${still})` } : undefined} />
            </div>
            <div className="feed-caption">
              {clip.sentences[0] && (
                <>
                  <p className="feed-line-en">{clip.sentences[0].text_en}</p>
                  <p className="feed-line-zh">{clip.sentences[0].text_zh}</p>
                </>
              )}
            </div>
          </>
        )}

        <footer className="feed-info">
          <div className="feed-info-text">
            <span className="feed-show">{show.label}</span>
            <h2 className="feed-title">{clipTitle(clip)}</h2>
            <span className="feed-meta">
              {DIFFICULTY_LABELS[difficulty] && (
                <span className={`level level-${difficulty}`}>{DIFFICULTY_LABELS[difficulty]}</span>
              )}
              <span className="muted small">{formatDuration(clip.duration_ms)}</span>
            </span>
          </div>
          <Link to={`/reader/${clip.lesson_id}`} className="btn-hero ghost feed-open">
            Full lesson
            <span aria-hidden="true">→</span>
          </Link>
        </footer>
      </div>

      <nav className="feed-rail" aria-label="Clips">
        <button className="feed-rail-btn" onClick={onPrev} disabled={!onPrev} aria-label="Previous clip">
          <Chevron up />
        </button>
        <button className="feed-rail-btn" onClick={onNext} disabled={!onNext} aria-label="Next clip">
          <Chevron />
        </button>
      </nav>
    </section>
  )
}

/** The playing clip: the player, and the caption that follows it. */
function ActiveClip({
  clip,
  status,
}: {
  clip: FeedClip
  status?: ReadonlyMap<string, WordStatus>
}) {
  const { wrapRef, ready, playing, currentMs, controls } = useYouTubePlayer(clip.youtube_id)
  const [selected, setSelected] = useState<{ token: TokenSpan; lineIdx: number } | null>(null)

  // Until playback actually begins, YouTube draws its unstarted state — a
  // channel header, a red button, "Watch on YouTube". Our own still covers it,
  // as the Reader's poster does; it comes down once, on the first real play.
  const [started, setStarted] = useState(false)
  useEffect(() => {
    if (playing) setStarted(true)
  }, [playing])
  const still = stillOf(clip)

  // Start at the window's beginning once the player is ready.
  useEffect(() => {
    if (ready) {
      controls.seekMs(clip.start_ms)
      controls.play()
    }
  }, [ready, clip.start_ms, controls])

  // Loop within the clip window — but not while a word card is open, or the
  // clip would restart under the learner mid-lookup.
  useEffect(() => {
    if (ready && !selected && currentMs >= clip.end_ms) controls.seekMs(clip.start_ms)
  }, [ready, selected, currentMs, clip.end_ms, clip.start_ms, controls])

  // The line on screen is the last one to have started. Between lines (a
  // pause in speech) the previous line stays up rather than blanking.
  const lineIdx = useMemo(() => {
    if (!ready) return 0
    let idx = 0
    clip.sentences.forEach((s, i) => {
      if (s.start_ms <= currentMs) idx = i
    })
    return idx
  }, [ready, currentMs, clip.sentences])

  const line = clip.sentences[selected?.lineIdx ?? lineIdx]
  const progress = ready
    ? Math.min(1, Math.max(0, (currentMs - clip.start_ms) / clip.duration_ms))
    : 0

  const openWord = (token: TokenSpan) => {
    controls.pause()
    setSelected({ token, lineIdx })
  }

  const closeWord = () => {
    setSelected(null)
    controls.play()
  }

  return (
    <>
      <div className="feed-video">
        <div className="clip-player" ref={wrapRef} />
        {/* The iframe swallows clicks, and with native controls off it would
            not say what they did anyway: one surface, one meaning. */}
        <button
          className={playing ? 'feed-tap' : started ? 'feed-tap paused' : 'feed-tap unstarted'}
          style={!started && still ? { backgroundImage: `url(${still})` } : undefined}
          onClick={() => (playing ? controls.pause() : controls.play())}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {!playing && (
            <span className="feed-tap-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="30" height="30">
                <polygon points="8,5 20,12 8,19" fill="currentColor" />
              </svg>
            </span>
          )}
        </button>
        <span className="feed-progress" aria-hidden="true">
          <span style={{ transform: `scaleX(${progress})` }} />
        </span>
      </div>

      <div className="feed-caption" aria-live="polite">
        {line && (
          <>
            <TappableSentence
              key={line.id}
              sentence={line}
              onWordTap={openWord}
              status={status}
              className="feed-line-en"
            />
            <p className="feed-line-zh">{line.text_zh}</p>
          </>
        )}
      </div>

      {selected && line && (
        <div className="feed-word-sheet">
          <WordCard
            key={`${line.id}:${selected.token.char_span[0]}`}
            surface={selected.token.surface}
            lemma={selected.token.lemma}
            sentenceId={line.id}
            contextZh={line.text_zh}
            onClose={closeWord}
          />
        </div>
      )}
    </>
  )
}

function Chevron({ up = false }: { up?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path
        d={up ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
