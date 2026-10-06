// What onboarding asked, kept in localStorage.
//
// Level and a daily goal are preferences, not identity: they change the order
// of the explore shelves and the target on the review page, and nothing else.
// Putting them behind the account would mean the one screen that exists to
// make the product feel personal could not run until after the sign-up form,
// which is backwards — the tour comes before the ticket.
import { useCallback, useSyncExternalStore } from 'react'
import type { Difficulty } from '../library/useLessons'

const KEY = 'vidlingo.prefs'

export interface LearnerPrefs {
  level: Difficulty
  /** Words per day the review page aims at. */
  dailyGoal: number
  /** Set once onboarding has been completed or skipped, so it asks once. */
  onboardedAt: number | null
}

export const GOALS = [5, 10, 20] as const

export const DEFAULT_PREFS: LearnerPrefs = {
  // The middle of the three, because it is a guess about a person we have not
  // met — and because guessing "easy" at someone who is fluent is the more
  // annoying of the two ways to be wrong.
  level: 'medium',
  dailyGoal: 10,
  onboardedAt: null,
}

function read(): LearnerPrefs {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return DEFAULT_PREFS
    const p = JSON.parse(raw) as Partial<LearnerPrefs>
    return {
      level: p.level === 'medium' || p.level === 'hard' ? p.level : 'easy',
      dailyGoal: GOALS.includes(p.dailyGoal as (typeof GOALS)[number])
        ? (p.dailyGoal as number)
        : DEFAULT_PREFS.dailyGoal,
      onboardedAt: typeof p.onboardedAt === 'number' ? p.onboardedAt : null,
    }
  } catch {
    return DEFAULT_PREFS
  }
}

let snapshot: LearnerPrefs | null = null
const listeners = new Set<() => void>()

function getSnapshot(): LearnerPrefs {
  snapshot ??= read()
  return snapshot
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function savePrefs(next: Partial<LearnerPrefs>) {
  const merged = { ...getSnapshot(), ...next }
  snapshot = merged
  try {
    localStorage.setItem(KEY, JSON.stringify(merged))
  } catch {
    /* ignore */
  }
  listeners.forEach((fn) => fn())
}

export function useLearnerPrefs(): LearnerPrefs {
  return useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_PREFS)
}

export function useSavePrefs(): (next: Partial<LearnerPrefs>) => void {
  return useCallback((next: Partial<LearnerPrefs>) => savePrefs(next), [])
}
