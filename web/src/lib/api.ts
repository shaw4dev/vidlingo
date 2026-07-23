// Typed REST client over the VidLingo backend (arch §4.1 `lib/apiClient`).
// Types mirror the FastAPI response models in backend/app/routers/*.
//
// Base URL is `/api` by default (proxied to the backend in dev — see
// vite.config.ts). Override with VITE_API_BASE for a deployed backend.

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

const TOKEN_KEY = 'vidlingo.token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${BASE}${path}`, { ...init, headers })

  if (!res.ok) {
    // FastAPI errors are `{ detail: string | ... }`.
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---- types (mirror backend response models) --------------------------------

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: string
  username: string
  created_at: string
}

export interface LessonSummary {
  id: string
  provider: string
  youtube_id: string | null
  title: string
  theme: string
  difficulty: string | null
  duration_ms: number
  source: string | null
}

export interface TokenSpan {
  char_span: [number, number]
  surface: string
  lemma: string
  pos: string | null
  dict_ref: string | null
}

export interface Sentence {
  id: string
  idx: number
  start_ms: number
  end_ms: number
  text_en: string
  text_zh: string
  difficulty: string
  tokens: TokenSpan[]
}

export interface LessonDetail extends LessonSummary {
  sentences: Sentence[]
}

export interface Occurrence {
  lesson_id: string
  youtube_id: string | null
  lesson_title: string
  sentence_id: string
  idx: number
  start_ms: number
  text_en: string
  text_zh: string
}

export interface OccurrencesResponse {
  lemma: string
  count: number
  occurrences: Occurrence[]
}

export type Mastery = 'new' | 'learning' | 'mastered'

export interface SourceRef {
  sentence_id: string
  lesson_id: string
  lesson_title: string
  youtube_id: string | null
  idx: number
  start_ms: number
  text_en: string
  text_zh: string
}

export interface VocabItem {
  id: string
  lemma: string
  surface: string | null
  mastery: string
  note: string | null
  added_at: string
  source: SourceRef | null
}

// ---- endpoints -------------------------------------------------------------

export const api = {
  // auth (T04)
  register: (username: string, password: string) =>
    request<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>('/auth/me'),

  // content (T05)
  listLessons: (params: { theme?: string; difficulty?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.theme) q.set('theme', params.theme)
    if (params.difficulty) q.set('difficulty', params.difficulty)
    const qs = q.toString()
    return request<LessonSummary[]>(`/lessons${qs ? `?${qs}` : ''}`)
  },
  getLesson: (lessonId: string) => request<LessonDetail>(`/lessons/${lessonId}`),
  wordOccurrences: (lemma: string) =>
    request<OccurrencesResponse>(`/words/${encodeURIComponent(lemma)}/occurrences`),

  // vocab (T06, per-user)
  listVocab: () => request<VocabItem[]>('/vocab'),
  addVocab: (body: {
    lemma: string
    surface?: string
    source_sentence_id?: string
    note?: string
  }) => request<VocabItem>('/vocab', { method: 'POST', body: JSON.stringify(body) }),
  updateVocab: (id: string, body: { mastery?: Mastery; note?: string }) =>
    request<VocabItem>(`/vocab/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteVocab: (id: string) => request<void>(`/vocab/${id}`, { method: 'DELETE' }),
}
