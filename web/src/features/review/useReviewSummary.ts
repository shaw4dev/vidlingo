// How many words are waiting — the number on the nav tab, and the line at the
// top of the vocab list.
//
// Kept separate from the queue so the first screen never pays for twenty cards
// it is not going to show: this is two counts and no joins.
import { useEffect, useState } from 'react'
import { useAuth } from '../../auth/AuthContext'
import { api, type ReviewSummary } from '../../lib/api'
import { useLearnerPrefs } from '../prefs/useLearnerPrefs'

// Bumped after a grading so the badge does not sit there claiming work that is
// already done. A module-level counter rather than shared state: every
// consumer just refetches, and there is nothing to keep in sync.
let version = 0
const listeners = new Set<() => void>()

export function bumpReviewSummary() {
  version += 1
  for (const notify of listeners) notify()
}

export function useReviewSummary(): ReviewSummary | null {
  const { user } = useAuth()
  // Same cap the queue will use, or the nav badge promises more cards than
  // the session is going to deal out.
  const { dailyGoal } = useLearnerPrefs()
  const [summary, setSummary] = useState<ReviewSummary | null>(null)
  // The module counter is not a valid effect dependency -- mutating it renders
  // nothing. Mirroring it into state is what actually re-runs the fetch.
  const [tick, setTick] = useState(version)

  useEffect(() => {
    const refresh = () => setTick(version)
    listeners.add(refresh)
    return () => {
      listeners.delete(refresh)
    }
  }, [])

  useEffect(() => {
    if (!user) {
      setSummary(null)
      return
    }
    let live = true
    api
      .reviewSummary(dailyGoal)
      .then((s) => live && setSummary(s))
      // Silent: a badge that cannot load is a badge that should not appear,
      // not an error banner across someone's library page.
      .catch(() => live && setSummary(null))
    return () => {
      live = false
    }
  }, [user, tick, dailyGoal])

  return summary
}
