// Play exactly one sentence and stop at its end.
//
// This is the fiddliest behaviour in the app, and two screens need it: the
// Reader's auto-pause mode, and the review card's "play this line" button.
// It lived inline in ReaderPage until the review card wanted it too — one
// implementation, because two copies of a latch like this drift, and the drift
// shows up as a video that quietly runs past the end on one screen only.
//
// The latch is the whole trick. YouTube has no timeupdate event, so the end of
// a sentence is detected by polling getCurrentTime(); without a flag saying
// "already stopped for this one", every poll after the boundary would call
// pause() again, and the user could not scrub back or resume at all.
import { useCallback, useEffect, useRef } from 'react'
import type { PlayerControls } from './useYouTubePlayer'

export interface SentenceClip {
  /** Seek to the start of the span and play it. */
  playClip: () => void
  /** Forget that we already stopped — call before any manual seek.
   *
   *  Needed because `currentMs` lags a seek by a poll or two: relying on the
   *  "we are back inside the span" effect alone leaves a window where the
   *  latch is still set and the very next poll pauses playback again.
   */
  reset: () => void
}

export function useSentenceClip(opts: {
  ready: boolean
  playing: boolean
  currentMs: number
  controls: PlayerControls
  startMs: number | null
  endMs: number | null
  /** False while another mode owns the boundary (the Reader's loop / follow). */
  enabled?: boolean
}): SentenceClip {
  const { ready, playing, currentMs, controls, startMs, endMs, enabled = true } = opts
  const stopped = useRef(false)

  useEffect(() => {
    if (!enabled || !ready || endMs == null) return
    if (playing && currentMs >= endMs && !stopped.current) {
      stopped.current = true
      controls.pause()
    }
  }, [enabled, ready, playing, currentMs, endMs, controls])

  // Re-entering the span re-arms the stop, so replaying works without anyone
  // having to remember to clear the latch.
  useEffect(() => {
    if (endMs != null && currentMs < endMs) stopped.current = false
  }, [currentMs, endMs])

  const reset = useCallback(() => {
    stopped.current = false
  }, [])

  const playClip = useCallback(() => {
    if (startMs == null) return
    stopped.current = false
    controls.seekMs(startMs)
    controls.play()
  }, [startMs, controls])

  return { playClip, reset }
}
