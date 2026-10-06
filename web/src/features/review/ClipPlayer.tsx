// The clip attached to a review card: play this one line, stop at its end.
//
// Mounted once for the whole session, not once per card. `useYouTubePlayer`
// keys its effect on the video id, so a new id tears down the iframe and
// rebuilds it — a flash plus a second of buffering. Since useReviewQueue
// groups consecutive cards by video, most card changes are a seek and nothing
// more; only crossing into a different lesson costs a reload.
import { useEffect, useRef } from 'react'
import { useYouTubePlayer } from '../reader/useYouTubePlayer'
import { useSentenceClip } from '../reader/useSentenceClip'

export function ClipPlayer({
  youtubeId,
  startMs,
  endMs,
  /** Changes when the card does, so the clip can re-arm without remounting. */
  cardKey,
  /** Whether the answer is showing yet. Gates the play button, not the frame.
   *
   *  What leaks the answer is the audio, not the picture: a paused frame of the
   *  scene says nothing about which word was blanked, and is a fair visual cue.
   *  So the player stays on screen and only the button waits for the reveal.
   *
   *  This is also the only arrangement that works. A YT.Player built inside a
   *  display:none container never gets laid out, and stays dead after it is
   *  shown -- playVideo() does nothing and the frame is a black box. Hiding the
   *  whole clip on the front looked tidier and quietly broke playback.
   */
  revealed,
}: {
  youtubeId: string | null
  startMs: number | null
  endMs: number | null
  cardKey: string
  revealed: boolean
}) {
  const { wrapRef, ready, playing, currentMs, controls } = useYouTubePlayer(youtubeId)
  const clip = useSentenceClip({ ready, playing, currentMs, controls, startMs, endMs })

  // Park the playhead at the new card's line and stop whatever was still
  // running from the previous one. Without this, moving on mid-clip leaves the
  // old sentence playing under the next card's question.
  const lastCard = useRef<string | null>(null)
  useEffect(() => {
    if (!ready || lastCard.current === cardKey) return
    lastCard.current = cardKey
    controls.pause()
    clip.reset()
    if (startMs != null) controls.seekMs(startMs)
  }, [ready, cardKey, startMs, controls, clip])

  if (!youtubeId) return null

  return (
    <div className="review-clip">
      <div className="player-mount" ref={wrapRef} />
      {revealed && (
        <button
          type="button"
          className="btn-small"
          onClick={playing ? controls.pause : clip.playClip}
          disabled={!ready}
        >
          {playing ? '⏸ 暂停' : '▶ 播放这一句'}
        </button>
      )}
    </div>
  )
}
