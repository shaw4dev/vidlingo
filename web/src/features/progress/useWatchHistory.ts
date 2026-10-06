// "Continue watching", kept in localStorage.
//
// Deliberately not on the server. Where you stopped in a clip is not worth an
// account: a visitor who has not signed up is exactly the person the shelf has
// to work for, because a library that remembers you is the argument for coming
// back. Signing in later adds the saved words and the review schedule — the
// things that genuinely cannot live in one browser.
import { useCallback, useSyncExternalStore } from 'react'

const KEY = 'vidlingo.watching'
/** Enough for a shelf; beyond that it is a history page nobody asked for. */
const MAX = 12
/** Below this the shelf would fill with clips she opened and bounced off. */
const MIN_SENTENCES = 2

export interface WatchMark {
  lessonId: string
  /** Where to resume: the reader takes this as `?s=`. */
  sentenceIdx: number
  sentenceCount: number
  /** Epoch ms, so the shelf is most-recent-first. */
  at: number
}

function read(): WatchMark[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    // Anything could be in localStorage — an old schema, another tab's bug,
    // a person poking at devtools. Validate rather than trust.
    return parsed.filter(
      (m): m is WatchMark =>
        !!m &&
        typeof m.lessonId === 'string' &&
        Number.isInteger(m.sentenceIdx) &&
        Number.isInteger(m.sentenceCount) &&
        m.sentenceCount > 0 &&
        typeof m.at === 'number',
    )
  } catch {
    return []
  }
}

// useSyncExternalStore needs a stable snapshot: parsing on every render would
// hand React a new array each time and loop. Re-parse only when we write.
let snapshot: WatchMark[] | null = null
const listeners = new Set<() => void>()

function getSnapshot(): WatchMark[] {
  snapshot ??= read()
  return snapshot
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function commit(marks: WatchMark[]) {
  snapshot = marks
  try {
    localStorage.setItem(KEY, JSON.stringify(marks))
  } catch {
    /* private mode, quota — the shelf is a convenience, not a feature */
  }
  listeners.forEach((fn) => fn())
}

/** Record where she is in a lesson. Idempotent per position. */
export function markWatched(mark: Omit<WatchMark, 'at'>) {
  if (mark.sentenceCount < MIN_SENTENCES) return
  const current = getSnapshot()
  const existing = current.find((m) => m.lessonId === mark.lessonId)
  if (existing && existing.sentenceIdx === mark.sentenceIdx) return
  commit(
    [{ ...mark, at: Date.now() }, ...current.filter((m) => m.lessonId !== mark.lessonId)].slice(
      0,
      MAX,
    ),
  )
}

export function useWatchHistory(): WatchMark[] {
  return useSyncExternalStore(subscribe, getSnapshot, () => [])
}

export function useClearWatchHistory(): () => void {
  return useCallback(() => commit([]), [])
}

/** 0–1. A clip is "finished" near the end, not at the last sentence exactly —
 *  the closing line is often a sign-off nobody sits through. */
export function progressOf(mark: WatchMark): number {
  return Math.min(1, (mark.sentenceIdx + 1) / mark.sentenceCount)
}

export function isFinished(mark: WatchMark): boolean {
  return progressOf(mark) >= 0.95
}
