# Task Breakdown — VidLingo

| Field | Value |
|---|---|
| Doc version | v2.0 (re-scoped to a daily-use MVP with a real backend) |
| Companion to | `PRD_v1.md`, `architecture.md` (esp. ADR-001: YouTube-embed) |
| MVP tasks | 15 (T01–T15); T01–T07 + T09 done (T08 deferred) |
| Backlog | parked below (B1–B12) — pull from it only after the MVP is in daily use |
| Client | **Web app** (React + Vite + TS) per **ADR-002** — no Mac needed; native iOS parked in backlog |

## MVP goal (one sentence)
A usable **web app** where my girlfriend can (on any phone/laptop browser): **pick a lesson → watch a YouTube video with bilingual subtitles → repeat any sentence and record herself → tap unknown words for meaning → save them → and pull up *other videos containing that word*** — backed by a real server (Docker + AWS) that's ready for more users later.

### What's in vs. out (and why)
- **In**: video reader, sentence repeat + shadowing/recording, tap-word definition, vocab list, **word→video reverse lookup**, a backend (Postgres + API), a content pipeline, Docker, AWS deploy, minimal multi-user auth.
- **Out for now** (→ backlog): spaced-repetition review, AI recommendation, difficulty models, AI dialog/role-play, phoneme-level scoring, subscription, social. These are the *expansion* (and the deeper MLE portfolio depth); they don't block daily use.
- **Why a backend** (vs. a local-only app): the reverse-lookup feature needs a shared content library + word index, you want Docker/AWS practice, and you want room for more users. All three point to a server.

> **Honest scope note.** Adding reverse-lookup + shadowing + a server roughly doubles the minimal MVP. It's still one coherent, finishable loop with a clear finish line (Milestone M1). If it ever feels heavy, the cut line is: ship T01–T15 **minus the reverse-lookup half of T13**, which is the one feature that depends on having lots of content.

Legend — **P**: P0 = core daily loop, P1 = should, P2 = nice. **Maps to**: PRD §, arch §.

---

## Done
- **T01 ✅** Repo scaffold + CI (backend FastAPI `/health`, client placeholder, GitHub Actions).
- **T02 ✅** `LessonPackage` schema + validator (structure + semantic checks; YouTube-embed shape per ADR-001).
- **T03 ✅** Postgres data model + Alembic migrations (lessons/sentences/tokens/word_index/users/vocab).
- **T04 ✅** Minimal auth: register/login/me, JWT bearer + PBKDF2; `get_current_user` dependency.
- **T05 ✅** Content API: `GET /lessons`, `GET /lessons/{id}`, `GET /words/{lemma}/occurrences` (reverse lookup).
- **T06 ✅** Vocab API (per-user): `POST/GET/PATCH/DELETE /vocab`. *(Phase A backend complete.)*
- **T07 ✅** Content pipeline: `youtube_id` → captions → segment → tokenize/lemmatize → build+validate → load to DB.
- **T09 ✅** Dockerized: `backend/Dockerfile` + root `docker-compose.yml` (API + Postgres 16, healthcheck-gated, migrate-on-start). *Statically validated; runtime `docker compose up` pending Docker install on the dev machine.*

> **T08 (ingest 10–15 real lessons) — deferred**, not blocking: needs video curation + a translation key. Do it before/with Phase D so reverse lookup has content.

---

## Phase A — Backend foundation (T03–T06)

### T03 · Data model & migrations (Postgres)
- **Do**: Implement schema: `lesson/video` (incl. `youtube_id`), `sentence`, `token`, `word_index` (lemma → sentence → youtube_id → start_ms), `user`, `vocab_item`. Migrations + seed script.
- **Maps to**: arch §5.2; ADR-001
- **Depends on**: T02
- **Done when**: Migrations run clean; seed inserts one lesson + sentences + tokens.

### T04 · Minimal auth / user accounts (multi-user ready)
- **Do**: Lightweight account creation + token auth. Start simple (username/password or device-id), but model it as real users so multi-user works later.
- **Maps to**: arch §5.1
- **Depends on**: T03
- **Done when**: App can create a user and make authenticated calls; data is scoped per user.

### T05 · Content API (lessons + reverse lookup)
- **Do**: Endpoints: list lessons (theme/difficulty), get a lesson's `LessonPackage`, and **`GET /words/{lemma}/occurrences`** → other sentences/videos containing the word (powers reverse lookup).
- **Maps to**: PRD §6.3, §6.4; arch §5.1
- **Depends on**: T03
- **Done when**: Given a seeded lemma, the API returns its occurrences across lessons.

### T06 · Vocab API (per-user)
- **Do**: Save/list/delete vocab items (lemma/phrase + source sentence + added time + mastery flag), scoped to the user.
- **Maps to**: PRD §6.2; arch §5.2
- **Depends on**: T04
- **Done when**: Add a word via API, list it back, delete it.

---

## Phase B — Content pipeline & seed library (T07–T08)

### T07 · Content pipeline v0 (YouTube captions → LessonPackage → DB)
- **Do**: Script: `youtube_id` → fetch caption track (ASR fallback if none) → sentence-segment with start/end_ms → translate (LLM/API) → tokenize/lemmatize/POS into token spans → build `LessonPackage` + `word_index` rows → validate (T02) → load to DB. Idempotent; flags videos with no usable captions.
- **Maps to**: PRD §8; arch §6; ADR-001
- **Depends on**: T02, T03
- **Done when**: Running it on a `youtube_id` produces a validated lesson in the DB, ready to serve.

### T08 · Ingest 10–15 starter lessons
- **Do**: Pick 10–15 YouTube videos with good captions covering her high-frequency scenarios (greetings, café/ordering, travel, small talk). Run the pipeline; quick manual proof-read. Record source + license in `content/sources.md`.
- **Maps to**: PRD §2.1, §13 Q1
- **Depends on**: T07
- **Done when**: 10–15 lessons live; reverse lookup (T05) returns multiple hits for common words.

---

## Phase C — Containerize & deploy (your Docker / AWS practice)

### T09 · Dockerize (Dockerfile + docker-compose)
- **Do**: Backend `Dockerfile`; `docker-compose.yml` running API + Postgres locally; env via `.env`; one-command local bring-up. Run migrations in the container.
- **Maps to**: arch §12
- **Depends on**: T05 (something to run)
- **Done when**: `docker compose up` serves `/health` and the content API with a real Postgres.

### T10 · Deploy to AWS
- **Do**: Push image to **ECR**; run on **ECS Fargate** behind an ALB (HTTPS), with **RDS Postgres**. *(Simpler starter alt: one EC2 running docker-compose — fine to begin, then graduate to ECS.)* Secrets via SSM/Secrets Manager.
- **Maps to**: arch §12
- **Depends on**: T09
- **Done when**: The API is reachable at a public HTTPS URL from the phone; DB persists.

---

## Phase D — Web app: the daily-use loop (T11–T15)

> Client is a **React + Vite + TypeScript** SPA consuming the REST API (ADR-002, arch §4). Consolidated from the old 7-task iOS plan into 5 web tasks. Each still ships a visible slice.

### T11 · Web scaffold + auth + API client ✅
- **Do**: Vite React+TS app; routing (browse / reader); a typed `apiClient` over the backend; register/login using the T04 auth endpoints (store token, authenticated fetch); dev proxy to the API; app builds & serves.
- **Maps to**: arch §4.1 (`features/auth`, `lib/apiClient`)
- **Depends on**: T04, T05
- **Done when**: You can register/login in the browser and the app makes an authenticated call to the API.
- **Done** ✅ — `web/`: `lib/api.ts` (typed client for auth/content/vocab), `AuthContext` (token in localStorage → `/auth/me`), `ProtectedRoute`, Login/Browse/Reader pages, Vite `/api` dev proxy. Verified register→authenticated `/me`→lessons through the proxy; unauth `/me`→401. `npm run build` + lint clean.

### T12 · Reader — player + sentence-by-sentence + tappable bilingual subtitles ✅
- **Do**: YouTube **IFrame Player API** driven by sentence timestamps: play/pause, prev/next sentence, **single-sentence repeat/loop**, auto-pause at sentence end (polled time), speeds 0.5–1.5×. Subtitle layer renders token spans as **tappable**, current-sentence highlight, mode toggle 中英 / 仅英 / 仅中 / 关闭. *(Merges old T11 + T12.)*
- **Maps to**: PRD §6.1.1–6.1.3; arch ADR-001, ADR-002, §4.1
- **Depends on**: T11
- **Done when**: A lesson plays embedded; she can loop/step any single sentence; words are individually tappable; all four subtitle modes render.
- **Done** ✅ — `features/reader/`: `lib/youtube.ts` (IFrame API loader), `useYouTubePlayer` (React-safe lifecycle + polled time + controls), `TappableSentence` (token buttons from `char_span`), Reader page (prev/next/play/pause, repeat loop, auto-pause, 0.5–1.5× speed, 4 subtitle modes, click-to-jump transcript). Tapped word shows a chip (word card = T13). Build (tsc+vite) + lint clean. *Browser/visual acceptance best done against real content (T08) — the seeded sample's timestamps are fabricated and won't align with the actual video's audio.*

### T13 · Word card + add-to-vocab + reverse lookup
- **Do**: On word-tap, a card: phonetic, POS, gloss, in-context meaning, TTS audio. Buttons: **Add to vocab** (persists via T06 vocab API) and **More videos with this word** → a list of other sentences/videos containing that lemma (via T05 reverse lookup); tap one → open that lesson at that sentence. Dictionary from a free API/dataset, cached client-side. *(Merges old T13 + T16 — the differentiator.)*
- **Maps to**: PRD §6.1.3, §6.4 (差异化亮点); arch §4.2
- **Depends on**: T12, T06
- **Done when**: Tapping a word shows meaning fast; "Add to vocab" persists; for an unknown word she sees other real videos using it and can jump straight in.

### T14 · Shadowing — record & hear yourself
- **Do**: On the current sentence: 🎤 record via `getUserMedia`/`MediaRecorder` → replay **her own recording** next to the original; lightweight feedback (duration/volume/completion). `PronunciationScorer` seam for a future engine. Codec-agnostic (mobile Safari = mp4/aac).
- **Maps to**: PRD §6.1.4; arch §4.2, ADR-002
- **Depends on**: T12
- **Done when**: She records a sentence and plays back her own voice next to the original (works in mobile Safari).

### T15 · Home browse + vocab list
- **Do**: Home lists lessons by theme/difficulty → tap opens the Reader. Vocab page lists saved words (word, source thumbnail, original sentence, added time); tap → jump back to that sentence; mark mastered / delete. *(Merges old T15 + T17.)*
- **Maps to**: PRD §6.2, §6.3
- **Depends on**: T11, T13
- **Done when**: Browsing shows seeded lessons and opens playback; saved words appear and tapping one returns to its source sentence.

---

## Milestone

| Milestone | Tasks | Outcome |
|---|---|---|
| **M1 — Daily-use MVP** | T01–T15 | Full loop she can use every day in a browser: watch → repeat → shadow → tap → save → find more videos with that word. Backend live on AWS via Docker. |

---

## Backlog — expansion (do NOT start until M1 is in daily use)

These are the *growth* features and the deeper **MLE portfolio depth** (the reason for the server in the first place). Pull them in one at a time, each its own demo.

| # | Item | Why later |
|---|---|---|
| **B1** | CI/CD: auto build+push image, deploy to AWS on `main` | Comes after a manual deploy works (T10) |
| **B2** | Observability: logs, metrics, cost dashboard (LLM/ASR usage) | Needs real traffic |
| **B3** | Behavioural **event ingest** + data lake | Foundation for all ML below |
| **B4** | Spaced-repetition **review** (SM-2 / Leitner) on vocab | Nice retention feature, not core to "try it" |
| **B5** | **Difficulty model** (rules → learned) | Manual difficulty tags suffice for MVP |
| **B6** | **Feature store + offline eval harness** | The credible MLE artifact; needs B3 data |
| **B7** | **Recommendation** (two-stage retrieval/ranking) | Needs content scale + B3/B6 |
| **B8** | Adaptive difficulty controller | Needs B5/B6 |
| **B9** | **AI dialog / role-play** over Claude (level-constrained) | V3 feature; cost + guardrails |
| **B10** | Phoneme-level pronunciation scoring (real SDK) | Upgrades T14's lightweight scorer |
| **B11** | **Subscription** (reserved seam: entitlement check) | Ch.13 Q4 — designed, not built |
| **B12** | **Social / sharing** (reserved seam: event bus) | Ch.13 Q3 — designed, not built |

> Portfolio note: B3 → B6 → B7 is the spine of the MLE story (data → features → eval → model → serving). The MVP's backend, Docker, and AWS work (T03–T10) is the infra-engineering half of that same story.
