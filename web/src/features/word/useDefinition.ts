// Fetch a word's dictionary entry, cached client-side (T13).
//
// Two layers of cache in front of the API: a module-level Map (instant within a
// session) and localStorage (survives reloads). The backend caches too, but the
// point here is that tapping the same word twice must feel free — no spinner,
// no request. Entries are small; a heavy reader accumulates a few hundred KB.
import { useEffect, useState } from 'react'
import { api, ApiError, type WordDefinition } from '../../lib/api'

const STORAGE_PREFIX = 'vidlingo.dict.'

// `null` is a real cached value: "we asked, the word isn't in the dictionary".
const memory = new Map<string, WordDefinition | null>()

function readStored(word: string): WordDefinition | null | undefined {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + word)
    if (raw == null) return undefined
    return JSON.parse(raw) as WordDefinition | null
  } catch {
    return undefined // unparseable or storage unavailable — just re-fetch
  }
}

function store(word: string, value: WordDefinition | null) {
  memory.set(word, value)
  try {
    localStorage.setItem(STORAGE_PREFIX + word, JSON.stringify(value))
  } catch {
    /* quota full or private mode — the memory cache still works */
  }
}

export interface DefinitionState {
  definition: WordDefinition | null
  loading: boolean
  /** Set only for real failures — an unknown word is `definition: null`, not an error. */
  error: string | null
}

export function useDefinition(word: string | null): DefinitionState {
  const key = word?.trim().toLowerCase() ?? ''
  const cached = key ? (memory.get(key) ?? readStored(key)) : undefined

  const [state, setState] = useState<DefinitionState>(() => ({
    definition: cached ?? null,
    loading: Boolean(key) && cached === undefined,
    error: null,
  }))

  useEffect(() => {
    if (!key) {
      setState({ definition: null, loading: false, error: null })
      return
    }
    const hit = memory.get(key) ?? readStored(key)
    if (hit !== undefined) {
      if (hit !== null) memory.set(key, hit) // promote a localStorage hit
      setState({ definition: hit, loading: false, error: null })
      return
    }

    let live = true
    setState({ definition: null, loading: true, error: null })
    api
      .wordDefinition(key)
      .then((def) => {
        store(key, def)
        if (live) setState({ definition: def, loading: false, error: null })
      })
      .catch((err) => {
        // 404 = we know there's no entry; cache that so we don't ask again.
        if (err instanceof ApiError && err.status === 404) {
          store(key, null)
          if (live) setState({ definition: null, loading: false, error: null })
          return
        }
        // Anything else (502, offline) is transient — don't poison the cache.
        if (live) {
          setState({
            definition: null,
            loading: false,
            error: err instanceof ApiError ? err.message : 'Could not load the definition',
          })
        }
      })
    return () => {
      live = false
    }
  }, [key])

  return state
}
