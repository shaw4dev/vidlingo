// Front-page clip feed (Feature A): a TikTok-style vertical stream of 30-90s
// windows. The visible clip mounts a YouTube player looping its [start,end)
// window; the rest show a thumbnail until scrolled into view. Tapping a word in
// the caption opens its word-detail page (Feature B).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type FeedClip } from '../lib/api'
import { useAuth } from '../auth/AuthContext'
import { useYouTubePlayer } from '../features/reader/useYouTubePlayer'

const PAGE = 10

export function FeedPage() {
  const { logout } = useAuth()
  const [clips, setClips] = useState<FeedClip[]>([])
  const [nextOffset, setNextOffset] = useState<number | null>(0)
  const [error, setError] = useState<string | null>(null)
  const [activeIdx, setActiveIdx] = useState(0)
  const loadingRef = useRef(false)

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

  if (error) {
    return (
      <div className="page">
        <FeedHeader onLogout={logout} />
        <p className="error">{error}</p>
      </div>
    )
  }

  return (
    <div className="page feed-page">
      <FeedHeader onLogout={logout} />
      {clips.length === 0 ? (
        <p className="muted center">Loading feed…</p>
      ) : (
        <div className="feed-scroll">
          {clips.map((clip, i) => (
            <FeedItem
              key={clip.clip_id}
              clip={clip}
              active={i === activeIdx}
              onVisible={() => setActiveIdx(i)}
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

function FeedHeader({ onLogout }: { onLogout: () => void }) {
  return (
    <header className="topbar">
      <strong>VidLingo</strong>
      <span className="spacer" />
      <Link to="/browse" className="link">
        Browse
      </Link>
      <button className="link" onClick={onLogout}>
        Log out
      </button>
    </header>
  )
}

function FeedItem({
  clip,
  active,
  onVisible,
}: {
  clip: FeedClip
  active: boolean
  onVisible: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)

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

  return (
    <section className="feed-item" ref={ref}>
      {active && clip.youtube_id ? (
        <ClipPlayer clip={clip} />
      ) : (
        <div
          className="clip-poster"
          style={{
            backgroundImage: clip.youtube_id
              ? `url(https://i.ytimg.com/vi/${clip.youtube_id}/hqdefault.jpg)`
              : undefined,
          }}
        />
      )}
      <div className="feed-caption">
        <div className="feed-meta muted small">
          {clip.title} · {clip.theme} · {(clip.duration_ms / 1000).toFixed(0)}s
        </div>
        <TappableText text={clip.text_en} />
      </div>
    </section>
  )
}

function ClipPlayer({ clip }: { clip: FeedClip }) {
  const { wrapRef, ready, currentMs, controls } = useYouTubePlayer(clip.youtube_id)

  // Start at the window's beginning once the player is ready.
  useEffect(() => {
    if (ready) {
      controls.seekMs(clip.start_ms)
      controls.play()
    }
  }, [ready, clip.start_ms, controls])

  // Loop within the clip window (TikTok-style repeat).
  useEffect(() => {
    if (ready && currentMs >= clip.end_ms) controls.seekMs(clip.start_ms)
  }, [ready, currentMs, clip.end_ms, clip.start_ms, controls])

  return <div className="clip-player" ref={wrapRef} />
}

// Render text with each word tappable -> word-detail page.
function TappableText({ text }: { text: string }) {
  const parts = text.split(/(\b[A-Za-z']+\b)/)
  return (
    <p className="feed-text">
      {parts.map((part, i) =>
        /^[A-Za-z']+$/.test(part) ? (
          <Link key={i} to={`/word/${encodeURIComponent(part.toLowerCase())}`} className="feed-word">
            {part}
          </Link>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </p>
  )
}
