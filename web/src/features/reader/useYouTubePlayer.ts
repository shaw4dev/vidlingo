// React hook wrapping a YouTube IFrame player (arch §4.1 PlayerEngine).
//
// The IFrame API replaces the element you hand it with an <iframe>. To avoid
// React and YouTube fighting over the same DOM node, we let React own only an
// outer wrapper and create/append the host node YouTube replaces ourselves.
//
// There is no timeupdate event, so we poll getCurrentTime() to drive
// sentence tracking, auto-pause, and looping.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loadYouTubeApi, type YTPlayer } from '../../lib/youtube'

export interface PlayerControls {
  play: () => void
  pause: () => void
  seekMs: (ms: number) => void
  setRate: (rate: number) => void
}

export function useYouTubePlayer(youtubeId: string | null) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<YTPlayer | null>(null)
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [currentMs, setCurrentMs] = useState(0)

  useEffect(() => {
    const wrap = wrapRef.current
    if (!youtubeId || !wrap) return

    let cancelled = false
    let player: YTPlayer | null = null
    const host = document.createElement('div')
    wrap.appendChild(host)

    loadYouTubeApi().then((YT) => {
      if (cancelled) return
      player = new YT.Player(host, {
        videoId: youtubeId,
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
        events: {
          onReady: (e) => {
            playerRef.current = e.target
            setReady(true)
          },
          onStateChange: (e) => setPlaying(e.data === YT.PlayerState.PLAYING),
        },
      })
    })

    return () => {
      cancelled = true
      setReady(false)
      setPlaying(false)
      playerRef.current = null
      try {
        player?.destroy()
      } catch {
        /* player may not have finished constructing */
      }
      if (host.parentNode) host.parentNode.removeChild(host)
    }
  }, [youtubeId])

  // Poll playback position while ready.
  useEffect(() => {
    if (!ready) return
    const id = window.setInterval(() => {
      const p = playerRef.current
      if (p) setCurrentMs(Math.round(p.getCurrentTime() * 1000))
    }, 120)
    return () => window.clearInterval(id)
  }, [ready])

  const controls: PlayerControls = useMemo(
    () => ({
      play: () => playerRef.current?.playVideo(),
      pause: () => playerRef.current?.pauseVideo(),
      seekMs: (ms) => playerRef.current?.seekTo(ms / 1000, true),
      setRate: (rate) => playerRef.current?.setPlaybackRate(rate),
    }),
    [],
  )

  const setRate = useCallback(
    (rate: number) => playerRef.current?.setPlaybackRate(rate),
    [],
  )

  return { wrapRef, ready, playing, currentMs, controls, setRate }
}
