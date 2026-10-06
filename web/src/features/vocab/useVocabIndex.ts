// Every saved word as a lemma → status lookup, so a transcript can tint the
// words she already cares about.
//
// This is the Language Reactor idea: the point of a word list is not the list,
// it is seeing the list *in the subtitles*. A word she saved yesterday should
// be visible as a saved word the next time it turns up in a different show,
// without her having to remember she saved it.
//
// One fetch per session, shared by every transcript, with an optimistic insert
// when she saves from the word card — re-fetching the whole list to learn a
// fact we just caused would make the tint arrive a round trip late.
import { useEffect, useSyncExternalStore } from 'react'
import { api, type VocabItem } from '../../lib/api'

// The same three states the vocab page shows on its pills, and the same three
// Language Reactor marks in subtitles. An earlier version collapsed new into
// learning, which put an amber "learning" tint on a word the vocab list was
// simultaneously labelling "New" — two screens disagreeing about one word.
export type WordStatus = 'new' | 'learning' | 'mastered'

export interface VocabIndex {
  /** Keyed by lemma, lowercased — what the tokeniser hands us. */
  status: ReadonlyMap<string, WordStatus>
  /** False until the first fetch resolves, so nothing flashes untinted. */
  ready: boolean
}

const EMPTY: VocabIndex = { status: new Map(), ready: false }

let snapshot: VocabIndex = EMPTY
let inFlight: Promise<void> | null = null
const listeners = new Set<() => void>()

function publish(next: VocabIndex) {
  snapshot = next
  listeners.forEach((fn) => fn())
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function statusOf(item: VocabItem): WordStatus {
  return item.mastery === 'mastered' || item.mastery === 'learning' ? item.mastery : 'new'
}

function load() {
  inFlight ??= api
    .listVocab()
    .then((items) => {
      publish({ status: new Map(items.map((i) => [i.lemma.toLowerCase(), statusOf(i)])), ready: true })
    })
    .catch(() => {
      // A failed lookup means no tint, which is the same as a new account.
      // Nothing here is worth an error banner over the transcript.
      publish({ status: new Map(), ready: true })
    })
    .finally(() => {
      inFlight = null
    })
}

/** Called after a successful save so the word tints immediately. */
export function noteWordSaved(lemma: string) {
  const next = new Map(snapshot.status)
  // A word saved a second ago has no review history, which is exactly what the
  // server will call it when we next ask.
  next.set(lemma.toLowerCase(), 'new')
  publish({ status: next, ready: snapshot.ready })
}

/** Called on logout, and after anything that rewrites the list wholesale. */
export function resetVocabIndex() {
  publish(EMPTY)
}

/**
 * @param enabled False for a signed-out visitor: there is no list to fetch,
 *   and a 401 per transcript is noise.
 */
export function useVocabIndex(enabled: boolean): VocabIndex {
  const state = useSyncExternalStore(subscribe, () => snapshot, () => EMPTY)

  useEffect(() => {
    if (!enabled) {
      if (snapshot !== EMPTY) resetVocabIndex()
      return
    }
    if (!state.ready) load()
  }, [enabled, state.ready])

  return enabled ? state : EMPTY
}
