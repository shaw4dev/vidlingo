# Task Breakdown — VidLingo

| Field | Value |
|---|---|
| Doc version | v1.0 |
| Companion to | `PRD_v1.md`, `architecture.md` |
| Total subtasks | 30 |
| Sequencing | Phases are roughly ordered; within a phase, tasks can overlap. Dependencies noted per task. |

> **How to use this.** Each task is sized to be finishable in roughly a day or two of solo work and ends in something demoable or testable. The "Demo / Done when" line is the acceptance check — and, for the portfolio goal, the thing you can show in an interview. IDs are stable; reference them in commits (e.g. `T07: tappable subtitle layer`).

Legend — **P**: priority (P0 must-have for that version, P1 should, P2 nice). **Maps to**: PRD §, architecture §.

---

## Phase 0 — Foundations (T01–T05)

### T01 · Repo, project scaffold & CI
- **Do**: Init git repo, iOS app skeleton (SwiftUI), backend skeleton (FastAPI), shared `.editorconfig`/lint, basic CI (lint + test + build).
- **Maps to**: arch §4, §5, §12.
- **Depends on**: —
- **Demo / Done when**: `main` builds the empty app and the API health endpoint in CI green.

### T02 · `LessonPackage` schema & validator
- **Do**: Define the JSON schema for a lesson package (video meta + sentences[start_ms/end_ms/text_en/text_zh/difficulty] + token spans + index rows). Write a schema validator usable in CI.
- **Maps to**: PRD §6.1, §8; arch §3, §6, §12.
- **Depends on**: T01
- **Demo / Done when**: A hand-authored sample package validates; a malformed one fails CI.

### T03 · Core data model & migrations (backend)
- **Do**: Implement Postgres schema from arch §5.2 (Video, Sentence, Token, WordVideoIndex, User, VocabItem, Event, ReviewSchedule, Entitlement) with migrations.
- **Maps to**: arch §5.2
- **Depends on**: T01
- **Demo / Done when**: Migrations run clean; seed script inserts one sample video + sentences.

### T04 · Auth & user bootstrap
- **Do**: Minimal account creation + session/token auth (`user-api`). Single-user is fine for MVP but keep the model multi-user.
- **Maps to**: arch §5.1
- **Depends on**: T03
- **Demo / Done when**: App can create a user and make an authenticated call.

### T05 · Event ingest endpoint + local event log
- **Do**: `POST /events` (batched, append-only) on backend; on-device SQLite event log + emitter (`Core/Analytics`). This is the flywheel foundation.
- **Maps to**: arch §3 (principle 4), §5.1, §7
- **Depends on**: T03, T04
- **Demo / Done when**: A tap event logged on-device appears in the backend event table after sync.

---

## Phase 1 — V1.0 MVP: the Reader loop (T06–T16)

> The heart of the product (PRD §6.1). Everything here is P0 unless noted.

### T06 · PlayerEngine: sentence-precise playback
- **Do**: `AVPlayer` wrapper driven by sentence timestamps: play/pause on tap, seek-to-sentence, auto-pause at sentence end.
- **Maps to**: PRD §6.1.2; arch §4.1
- **Depends on**: T02
- **Demo / Done when**: Tapping video toggles play/pause; sentence boundaries respected.

### T07 · Swipe navigation + single-sentence loop + speed
- **Do**: Left/right swipe = prev/next sentence; single-sentence loop button; rates 0.5/0.75/1/1.25/1.5×; draggable progress bar snapping to sentence start.
- **Maps to**: PRD §6.1.2
- **Depends on**: T06
- **Demo / Done when**: All transport controls work smoothly on the sample video.

### T08 · Tappable subtitle renderer + 3-state subtitle mode
- **Do**: Custom subtitle layer rendering token spans as tappable; current-sentence highlight; mode toggle 中英 / 仅英 / 仅中 / 关闭.
- **Maps to**: PRD §6.1.1, §6.1.3
- **Depends on**: T02, T06
- **Demo / Done when**: Words are individually tappable; all four subtitle modes render correctly.

### T09 · Word definition card + dictionary lookup
- **Do**: Bottom card on word-tap: phonetic, POS, gloss, in-context meaning, TTS playback. On-device dictionary cache backed by `content-api`/dictionary source.
- **Maps to**: PRD §6.1.3; arch §4.2 (< 200ms)
- **Depends on**: T08
- **Demo / Done when**: Tapping a word shows the card in < 200ms (cached) with audio playback.

### T10 · Phrase selection (long-press)
- **Do**: Long-press to select multi-word phrases; card adapts to phrase.
- **Maps to**: PRD §6.1.3
- **Priority**: P1
- **Depends on**: T09
- **Demo / Done when**: A 2–3 word phrase can be selected and looked up.

### T11 · ShadowingRecorder: record, compare, lightweight score
- **Do**: Record current sentence, replay vs. original, lightweight score (volume/duration/completion). Define `PronunciationScorer` protocol for the future SDK swap.
- **Maps to**: PRD §6.1.4; arch §4.2
- **Depends on**: T06
- **Demo / Done when**: User records a sentence, hears playback, sees a basic score; protocol seam exists.

### T12 · Vocab book (add / list / navigate back)
- **Do**: "Add to vocab" from word card; vocab list with word/phrase, source thumbnail, source sentence, added time; tap → jump back to source sentence. Mastery flag + delete.
- **Maps to**: PRD §6.2
- **Depends on**: T09
- **Demo / Done when**: Add a word, see it in the list, tap to return to its sentence in the video.

### T13 · Browse by theme × difficulty
- **Do**: Home grid filtering by theme (ordering/small-talk/travel/work…) and difficulty (easy/medium/hard, manual labels for MVP).
- **Maps to**: PRD §6.3
- **Depends on**: T03, content from T15/T16
- **Demo / Done when**: Filtering shows the right videos; tapping opens the Reader.

### T14 · ContentCache: offline package download & store
- **Do**: Download `LessonPackage` (video + subtitle/token data) to device; serve Reader from cache; basic cache management.
- **Maps to**: PRD §10; arch §3, §4.3
- **Depends on**: T02, T06
- **Demo / Done when**: A downloaded lesson plays fully in airplane mode.

### T15 · Content pipeline v0: ASR → sentence alignment
- **Do**: Script: raw video → ASR API → sentence segmentation with start/end_ms. Idempotent, outputs intermediate artifacts.
- **Maps to**: PRD §8; arch §6 (steps 1–2)
- **Depends on**: T02
- **Demo / Done when**: A raw clip produces sentence-timestamped transcript.

### T16 · Content pipeline v0: translate + tokenize + package + publish
- **Do**: Translate sentences (LLM/API), tokenize/lemmatize/POS into token spans, assemble + validate `LessonPackage`, upload to object storage/CDN, register in DB. Manual review step (approve/correct).
- **Maps to**: PRD §8; arch §6 (steps 3–4, 7–8)
- **Depends on**: T15, T02, T03
- **Demo / Done when**: One end-to-end real clip becomes a playable, validated, published lesson. **← V1.0 demo milestone.**

---

## Phase 2 — V1.5: context-web + review (T17–T21)

### T17 · Difficulty labelling v1 (rules)
- **Do**: Heuristic `DifficultyEstimator` (CEFR word-frequency bands, sentence length, speech rate) wired into the pipeline (step 5).
- **Maps to**: PRD §6.3; arch §6 (step 5), §3 (rules→model)
- **Depends on**: T16
- **Demo / Done when**: Pipeline auto-assigns easy/medium/hard; spot-check agrees with intuition.

### T18 · WordVideoIndex builder (inverted index)
- **Do**: Pipeline step building `lemma → sentence → video → start_ms` rows across the whole library.
- **Maps to**: PRD §6.4; arch §5.2, §6 (step 6)
- **Depends on**: T16
- **Demo / Done when**: Querying a lemma returns all its occurrences across videos.

### T19 · Word↔video reverse lookup (API + UI)
- **Do**: `content-api` endpoint + "see more video examples" entry on the word card → list of clips → tap jumps to that sentence.
- **Maps to**: PRD §6.1.3, §6.4
- **Depends on**: T18, T09
- **Demo / Done when**: From a word card, browse and jump into another video where the word appears. **← differentiator demo.**

### T20 · Review scheduling (SM-2 / Leitner)
- **Do**: `review-svc` scheduling vocab items by interval/ease; due-queue API; client `Feature/Review` tab.
- **Maps to**: PRD §6.5; arch §5.1
- **Depends on**: T12
- **Demo / Done when**: Added words surface for review on schedule.

### T21 · Contextual review UI + search & favorites
- **Do**: Review presents the word *in its original video sentence* (not a bare card); add search and a favorites/collection. Vocab grouping.
- **Maps to**: PRD §6.2, §6.5
- **Priority**: P1
- **Depends on**: T20, T14
- **Demo / Done when**: Reviewing replays the source sentence; search finds vocab/videos.

---

## Phase 3 — V2.0: personalization & the MLE spine (T22–T26)

### T22 · Feature store + feature-build job
- **Do**: Define user/content feature schemas (clicked word-families, themes, completion rates, level); batch job from event lake → feature tables (Parquet/Postgres).
- **Maps to**: arch §7
- **Depends on**: T05
- **Demo / Done when**: Running the job produces documented, inspectable feature tables.

### T23 · Eval harness + model registry conventions
- **Do**: Held-out sets, metric definitions (ranking metrics; difficulty-vs-human agreement), versioned model artifacts with training-data hash + metrics manifest.
- **Maps to**: arch §7 (the credibility piece)
- **Depends on**: T22
- **Demo / Done when**: A dummy model is registered with metrics; eval report regenerates reproducibly. **← strongest MLE artifact.**

### T24 · Onboarding placement test
- **Do**: 5–10 item quick test (listen/choose/shadow) → initial level.
- **Maps to**: PRD §6.6
- **Depends on**: T11, T04
- **Demo / Done when**: New user completes test and receives a starting level + difficulty.

### T25 · Recommender (two-stage) + serving
- **Do**: Candidate gen (level/theme filter) → ranking (behavioural model from features) → business rules (dedup/diversity/license). Serve via `ml-serving`; Discover feed.
- **Maps to**: PRD §6.6; arch §7, §8
- **Depends on**: T22, T23, T13
- **Demo / Done when**: Feed reorders sensibly per user; predictions logged back to event lake.

### T26 · Adaptive difficulty controller + difficulty model v2
- **Do**: Feedback controller (completion + tap-density → difficulty nudge); train difficulty model v2 calibrated on behaviour, behind existing `DifficultyEstimator` interface.
- **Maps to**: PRD §6.6; arch §6, §8
- **Depends on**: T17, T23
- **Demo / Done when**: Difficulty surfaced to a user adapts over sessions; v2 beats rules on eval.

---

## Phase 4 — V3.0: output & practice (T27–T28)

### T27 · DialogOrchestrator over Claude (scenario role-play)
- **Do**: `ml-serving` dialog orchestrator: scenario system prompt + level/vocab constraints + guardrails; turn caps + token logging; end-of-session feedback (nativeness, better phrasings).
- **Maps to**: PRD §6.7; arch §9
- **Depends on**: T24, T05
- **Demo / Done when**: A café-ordering role-play stays at the user's level and returns useful feedback; token cost logged.

### T28 · Phoneme-level pronunciation scoring
- **Do**: Integrate a pronunciation-eval SDK behind the existing `PronunciationScorer` protocol; consent + privacy flow for uploads.
- **Maps to**: PRD §6.1.4, §10; arch §4.2, §9
- **Depends on**: T11
- **Demo / Done when**: Shadowing returns phoneme-level scores; consent gated.

---

## Phase 5 — Reserved seams & wrap-up (T29–T30)

### T29 · Reserved seams: Entitlement + SocialEventBus stubs
- **Do**: `EntitlementService` returning `free` + `entitlement.can(feature)` gate call sites; no-op `SocialEventBus` publishing achievement events. No real subscription/social UI.
- **Maps to**: PRD Ch.13 Q3/Q4; arch §10
- **Depends on**: T04, T05
- **Demo / Done when**: Feature gates route through entitlement; achievement events publish to the no-op bus — both swappable later.

### T30 · Portfolio write-up: metrics dashboard + product story
- **Do**: North-Star instrumentation (weekly effective learned sentences) + a retrospective doc telling the product/ML story with data and trade-offs (why A-class first, what was cut and why).
- **Maps to**: PRD §4, §12; arch §7, §13
- **Depends on**: T05, T23, T25
- **Demo / Done when**: A dashboard shows the North Star + funnel; the write-up is interview-ready. **← the job-hunt deliverable.**

---

## Milestone map

| Milestone | Tasks | Demoable outcome |
|---|---|---|
| **M1 — V1.0 MVP** | T01–T16 | Full Reader loop:精读 + 跟读 + 生词本 on real content |
| **M2 — V1.5** | T17–T21 | Word↔video reverse lookup + contextual spaced review |
| **M3 — V2.0** | T22–T26 | Placement test + recommender + adaptive difficulty, all evaluated |
| **M4 — V3.0** | T27–T28 | AI role-play + phoneme scoring |
| **M5 — Reserve & story** | T29–T30 | Monetisation/social seams in place; portfolio narrative done |
