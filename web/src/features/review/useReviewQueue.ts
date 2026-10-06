// The review session: today's cards, and what happens when one is graded.
//
// Two deliberate departures from the house hook shape (useLessons.ts):
//
// 1. No module-level promise cache. The queue is per-user, mutable and
//    time-sensitive; caching it would serve a stale session after a reload and
//    show cards that were already answered.
// 2. Cards are reordered on arrival. The server picks *which* cards by due
//    date — that is the algorithm and it is not ours to second-guess — but
//    presentation order is a different question, and grouping by video avoids
//    tearing down and rebuilding the YouTube iframe between consecutive cards.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type Grade, type ReviewCard, type ReviewQueue } from '../../lib/api'
import { useLearnerPrefs } from '../prefs/useLearnerPrefs'

export interface ReviewSession {
  /** Null while loading. */
  cards: ReviewCard[] | null
  error: string | null
  index: number
  done: number
  cap: number
  dueTotal: number
  /** The card on screen, or null when the session is finished. */
  current: ReviewCard | null
  grade: (card: ReviewCard, grade: Grade, latencyMs?: number) => void
}

/** Keep consecutive cards on the same video where possible.
 *
 *  `useYouTubePlayer` keys its effect on the video id, so a different id means
 *  a fresh iframe: a visible flash and a second of buffering. At twenty cards
 *  that is most of the session spent waiting. Grouping costs nothing and the
 *  scheduler does not care what order today's allowance is answered in.
 */
export function groupByVideo(cards: ReviewCard[]): ReviewCard[] {
  const groups = new Map<string, ReviewCard[]>()
  for (const card of cards) {
    const key = card.source?.youtube_id ?? ''
    const bucket = groups.get(key)
    if (bucket) bucket.push(card)
    else groups.set(key, [card])
  }
  return [...groups.values()].flat()
}

export function useReviewQueue(): ReviewSession {
  // Onboarding asked for a daily number and promised the queue would stop
  // there. The server already takes a cap as `limit`, so honouring it is one
  // argument — and a promise the UI makes has to be one the UI keeps.
  const { dailyGoal } = useLearnerPrefs()
  const [cards, setCards] = useState<ReviewCard[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [meta, setMeta] = useState({ done: 0, cap: 0, dueTotal: 0 })

  // One id per card, minted when the queue arrives rather than at the tap.
  // A retry after a failed request has to carry the same id, or the server's
  // idempotency guard never engages and the schedule advances twice.
  const eventIds = useRef(new Map<string, string>())

  useEffect(() => {
    let live = true
    api
      .reviewQueue(dailyGoal)
      .then((queue: ReviewQueue) => {
        if (!live) return
        for (const card of queue.cards) {
          if (!eventIds.current.has(card.vocab_item_id)) {
            eventIds.current.set(card.vocab_item_id, newEventId())
          }
        }
        setCards(groupByVideo(queue.cards))
        setMeta({ done: queue.done_today, cap: queue.cap, dueTotal: queue.due_total })
      })
      .catch((err) => {
        if (!live) return
        setError(err instanceof ApiError ? err.message : 'Failed to load your review queue')
      })
    return () => {
      live = false
    }
  }, [dailyGoal])

  const grade = useCallback((card: ReviewCard, grade: Grade, latencyMs?: number) => {
    // Optimistic, in the house style: advance now, step back if the API
    // refuses. Waiting for the round trip would put a spinner between every
    // card, which is most of what a review session is.
    setIndex((i) => i + 1)
    setMeta((m) => ({ ...m, done: m.done + 1 }))

    const eventId = eventIds.current.get(card.vocab_item_id) ?? newEventId()
    eventIds.current.set(card.vocab_item_id, eventId)

    api
      .gradeReview({
        client_event_id: eventId,
        vocab_item_id: card.vocab_item_id,
        grade,
        latency_ms: latencyMs,
      })
      .catch((err) => {
        setIndex((i) => Math.max(0, i - 1))
        setMeta((m) => ({ ...m, done: Math.max(0, m.done - 1) }))
        setError(err instanceof ApiError ? err.message : 'Could not save that answer')
      })
  }, [])

  return {
    cards,
    error,
    index,
    done: meta.done,
    cap: meta.cap,
    dueTotal: meta.dueTotal,
    current: cards && index < cards.length ? cards[index] : null,
    grade,
  }
}

function newEventId(): string {
  // randomUUID needs a secure context; plain http on a LAN address is not one,
  // so keep a fallback rather than throwing in the middle of a session.
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `evt-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}
