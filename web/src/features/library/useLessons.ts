// The lesson list, fetched once per session and shared.
//
// Two callers need the *same* list in the *same* order: the library grid, and
// the reader's prev/next lesson arrows — "next" only makes sense as "next in
// the list she was just looking at". Filtering is therefore done here, on the
// client, rather than by re-querying `/lessons?difficulty=`: the library is
// small enough that one fetch beats one per filter click, and it keeps the two
// views from disagreeing about order. The server-side filters still exist for
// when the library outgrows this.
import { useEffect, useState } from 'react'
import { api, ApiError, type LessonSummary } from '../../lib/api'

export const DIFFICULTIES = ['easy', 'medium', 'hard'] as const
export type Difficulty = (typeof DIFFICULTIES)[number]

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: 'Easy',
  medium: 'Medium',
  hard: 'Hard',
}

let cache: Promise<LessonSummary[]> | null = null

function fetchLessons(): Promise<LessonSummary[]> {
  cache ??= api.listLessons().catch((err) => {
    cache = null // a failed fetch must not become the cached answer
    throw err
  })
  return cache
}

export interface LessonsState {
  lessons: LessonSummary[] | null
  error: string | null
}

export function useLessons(): LessonsState {
  const [state, setState] = useState<LessonsState>({ lessons: null, error: null })

  useEffect(() => {
    let live = true
    fetchLessons()
      .then((lessons) => live && setState({ lessons, error: null }))
      .catch((err) => {
        if (!live) return
        setState({
          lessons: null,
          error: err instanceof ApiError ? err.message : 'Failed to load lessons',
        })
      })
    return () => {
      live = false
    }
  }, [])

  return state
}

/** `mm:ss`, or `h:mm:ss` past the hour. */
export function formatDuration(ms: number): string {
  const total = Math.round(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h ? String(m).padStart(2, '0') : String(m)
  return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`
}

/** Which levels the corpus actually contains, in order.
 *
 *  Filters and shelves are built from this rather than from DIFFICULTIES: the
 *  library holds no easy clips today, and an "Easy" chip that always returns
 *  "nothing matches" reads as a broken filter, not as an honest catalogue. */
export function levelsPresent(lessons: LessonSummary[]): Difficulty[] {
  const present = new Set(lessons.map((l) => l.difficulty))
  return DIFFICULTIES.filter((d) => present.has(d))
}

/** The closest level to `want` that has at least `min` clips, or null.
 *
 *  Someone who told onboarding they are a beginner should still get a top
 *  shelf; it should just be the gentlest thing we actually have. */
export function nearestLevel(
  lessons: LessonSummary[],
  want: Difficulty,
  min = 3,
): Difficulty | null {
  const counts = new Map<Difficulty, number>()
  for (const l of lessons) {
    const d = l.difficulty as Difficulty | null
    if (d) counts.set(d, (counts.get(d) ?? 0) + 1)
  }
  const wantAt = DIFFICULTIES.indexOf(want)
  return (
    [...DIFFICULTIES]
      .filter((d) => (counts.get(d) ?? 0) >= min)
      .sort((a, b) => Math.abs(DIFFICULTIES.indexOf(a) - wantAt) - Math.abs(DIFFICULTIES.indexOf(b) - wantAt))[0] ?? null
  )
}

export function thumbnailUrl(youtubeId: string | null): string | undefined {
  return youtubeId ? `https://i.ytimg.com/vi/${youtubeId}/hqdefault.jpg` : undefined
}
