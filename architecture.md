# Architecture Design — VidLingo (Video English Learning App)

| Field | Value |
|---|---|
| Doc version | v1.0 |
| Companion to | `PRD_v1.md` |
| Author intent | (1) Real product for daily use; (2) MLE portfolio artifact for the Australian job market |
| Reserved (designed, not built) | Commercial subscription (Ch.13 Q4), Social / check-in sharing (Ch.13 Q3) |
| Language note | Written in English to double as an interview / portfolio artifact |

> **Reading guide for reviewers / interviewers.** This document is structured around a single principle from the PRD: *ship one polished learning loop (§6.1), then layer intelligence on top of the same engine.* The ML-heavy sections (§6 Content Pipeline, §7 ML Platform, §8 Recommendation, §9 Conversation) are where the system-design depth lives; everything else is the minimum viable scaffolding that lets those parts exist.

---

## 1. Goals & Constraints

### 1.1 What the architecture must optimise for

| Driver | Source | Architectural consequence |
|---|---|---|
| **One demoable loop per version** | PRD §5, §12 | Vertical slices, not horizontal layers. Each version = a self-contained, deployable capability. |
| **< 200ms perceived latency** on play / sentence-switch / word-tap | PRD §10 | Word-tap data and subtitle timestamps must be **precomputed and shipped with content**, not fetched per tap. Dictionary lookups cached on-device. |
| **Offline / weak-network** (commute, subway) | PRD §10 | Content is cacheable and self-contained; user state syncs opportunistically (offline-first). |
| **MLE portfolio depth** | Author goal | Treat the **content pipeline + feature store + recommender + eval harness** as first-class, observable, reproducible systems — the things an MLE is hired to build. |
| **Single engine, many difficulty pools** | PRD §2.1 | No user-segment-specific code paths. Difficulty is *data + a model score*, never a fork. |
| **Reserve, don't build, monetisation & social** | Ch.13 | Define the seams (entitlement check, sharing event) as interfaces with no-op / stub implementations. |

### 1.2 Non-goals for MVP
- No payment processing, no social graph, no Android (PRD: iOS first).
- No phoneme-level pronunciation scoring in V1 (PRD §6.1.4 — lightweight only).
- No real-time multiplayer / live anything.

### 1.3 Guiding constraint: build-vs-buy
Author is a solo developer optimising for *demonstrating ML engineering*, not reinventing infra. Rule of thumb: **buy/borrow the undifferentiated heavy lifting (ASR, TTS, base LLM, dictionary), build the differentiating pipelines (forced alignment, word↔video inverted index, recommender, eval).**

---

## 2. System Context (C4 Level 1)

```
                         ┌───────────────────────────────────────────┐
                         │                 VidLingo                   │
                         │                                            │
   ┌──────────┐  HTTPS   │   ┌──────────┐      ┌─────────────────┐    │
   │  iOS App │◀────────▶│   │ Backend  │◀────▶│  ML Platform     │    │
   │ (learner)│  (REST/  │   │   API    │      │ (rec / dialog /  │    │
   └──────────┘   gRPC)  │   └────┬─────┘      │  scoring / eval) │    │
        ▲                 │       │            └─────────────────┘    │
        │ cached content  │       ▼                                   │
        │                 │   ┌──────────┐    ┌────────────────────┐  │
        │                 │   │ Content  │◀──▶│ Content Pipeline    │  │
        └─────────────────┼───│  Store   │    │ (ASR→align→index→   │  │
          CDN (video +    │   │ + CDN    │    │  difficulty label)  │  │
          subtitle pkg)   │   └──────────┘    └────────────────────┘  │
                         └────────────────────────────┬───────────────┘
                                                       │
        External: ASR API · TTS API · Dictionary API · LLM API (Claude)
                  Pronunciation-eval SDK (V3) · Object storage · CDN
```

**Actors**: the *learner* (girlfriend / future users), the *content editor* (you, doing ASR-proofreading), and *automated jobs* (pipeline, model training, review scheduling).

---

## 3. Architecture Principles

1. **Content is a build artifact.** A video isn't streamed-and-parsed at runtime; it's *compiled* offline into a `LessonPackage` (video + sentence-level bilingual subtitles + word-click metadata + difficulty label). The app renders a static package → cheap, fast, offline-friendly.
2. **Offline-first client, eventually-consistent state.** All learning interactions (taps, follow-reads, vocab adds) are logged locally and synced; the server is authoritative for cross-device merge only.
3. **Rules first, models later — behind the same interface.** Difficulty, review scheduling, and recommendation each ship as a *rule-based v1* implementing an interface the *model-based v2* later satisfies. No rewrite, just a swap. (Directly mirrors PRD §1.3 "渐进智能".)
4. **Every ML output is logged with its inputs.** Recommendations, difficulty scores, and dialog turns emit structured events → the same data trains the next model. The product *is* the data flywheel.
5. **Reserved seams are explicit, not implicit.** `EntitlementService` and `SocialEventBus` exist as interfaces from day one with trivial implementations, so adding subscription / social later is additive, not surgical.

---

## 4. Client Architecture (iOS)

**Stack**: Swift, SwiftUI, AVFoundation/`AVPlayer`, `AVAudioRecorder`, SQLite (GRDB) for local store, Combine/async-await.

### 4.1 Module map
```
App
├── Feature/Reader        ← §6.1 the heart: player + subtitle + word-tap + follow-read
│   ├── PlayerEngine       (AVPlayer wrapper: seek-to-sentence, single-sentence loop, rate 0.5–1.5×)
│   ├── SubtitleRenderer   (custom tappable token layer; current-sentence highlight)
│   ├── WordCard           (phonetic, POS, gloss, in-context meaning, TTS playback)
│   └── ShadowingRecorder  (record → align-to-original → lightweight score → replay)
├── Feature/Vocab         ← §6.2 vocab book (source thumbnail, sentence, mastery)
├── Feature/Browse        ← §6.3 theme × difficulty grid
├── Feature/Review        ← §6.5 spaced repetition (V1.5)
├── Feature/Discover      ← §6.6/§6.7 recommend + role-play (V2/V3)
├── Feature/Profile       ← level, stats, settings
├── Core/ContentCache      (LessonPackage download + offline store)
├── Core/SyncEngine        (offline event queue → backend; CRDT-lite last-write-wins per field)
├── Core/Analytics         (structured event emitter → the data flywheel)
└── Core/Entitlement       (RESERVED: returns .free always in MVP)
```

### 4.2 Why these choices
- **Sentence-level control** (PRD §6.1.2 left/right-swipe = prev/next sentence, auto-pause at sentence end, single-sentence loop) is exactly what `AVPlayer` + a sentence-timestamp table makes precise. The `PlayerEngine` is driven by the `LessonPackage` timestamps, never by guesswork.
- **Tappable subtitles render from precomputed token spans** shipped in the package → word-tap is a local dictionary lookup (cached), satisfying < 200ms (PRD §10) and working offline.
- **Follow-read scoring is local & lightweight in V1** (volume / duration / completion, PRD §6.1.4); the `ShadowingRecorder` exposes a `PronunciationScorer` protocol so the V3 phoneme-level SDK drops in without touching the UI.

### 4.3 Offline-first data flow
```
User taps word ──▶ local event log (SQLite) ──▶ UI updates instantly (local dict)
                                  │
                       SyncEngine (on connectivity) ──▶ POST /events (batched)
Vocab add ─────────▶ local vocab table ──▶ optimistic UI ──▶ sync ──▶ server merge
```

---

## 5. Backend Architecture

**Stack recommendation**: Python (FastAPI) for API + ML serving cohesion (one language across API and ML = less context-switching for a solo dev, and the *right* signal for an MLE role). PostgreSQL as primary store, Redis for cache/queues, object storage + CDN for media.

> Rationale for an MLE: choosing Python/FastAPI keeps the recommender, dialog orchestration, and eval harness in the same ecosystem as serving — you demonstrate end-to-end ML ownership, not just model training in a notebook.

### 5.1 Service decomposition (modular monolith → split later)
Start as a **modular monolith** (one deployable, clear module boundaries). Split to services only when a module needs independent scaling (likely: ML serving). This keeps solo-dev velocity while showing you understand service boundaries.

| Module | Responsibility | Storage |
|---|---|---|
| `content-api` | Serve `LessonPackage` manifests, browse-by-theme/difficulty, word↔video reverse lookup (V1.5) | Postgres + CDN |
| `user-api` | Auth, vocab book, learning records, level, sync merge | Postgres |
| `event-ingest` | Append-only behavioural event sink (the flywheel) | Postgres → object storage (cold) |
| `review-svc` | Spaced-repetition scheduling (V1.5) | Postgres |
| `ml-serving` | Recommendation (V2), dialog orchestration (V3), difficulty inference (V2) | model registry + feature store |
| `entitlement-svc` | **RESERVED**: subscription/entitlement checks. MVP = stub returning `free`. | — |
| `social-bus` | **RESERVED**: publish learning achievements for future sharing. MVP = no-op. | — |

### 5.2 Core data model (essentials)
```
Video(id, title, theme, source, license_tag, duration, cdn_url)
Sentence(id, video_id, idx, start_ms, end_ms, text_en, text_zh, difficulty)
Token(id, sentence_id, char_span, lemma, surface, pos, dict_ref)   ← drives word-tap
WordVideoIndex(lemma, sentence_id, video_id, start_ms)             ← word↔video inverted index (V1.5)
User(id, level, created_at)
VocabItem(id, user_id, lemma/phrase, source_sentence_id, mastery, added_at, review_state)
Event(id, user_id, type, payload_json, ts)                        ← taps, follow-reads, completions
ReviewSchedule(vocab_item_id, due_at, interval, ease)             ← SM-2/Leitner (V1.5)
Entitlement(user_id, tier, expires_at)                            ← RESERVED
```

The `WordVideoIndex` is the physical realisation of the PRD's differentiator (§6.4 "词→句→视频时间戳倒排索引") — built by the content pipeline, queried at runtime.

---

## 6. Content Pipeline (offline batch) — *first MLE-grade system*

This is the content factory from PRD §8/§9. It turns a raw video into a shippable `LessonPackage`. It is a batch DAG, reproducible and idempotent.

```
raw video ──▶ [1] ASR (external API)         ──▶ raw transcript + word timestamps
          ──▶ [2] Forced alignment / cleanup ──▶ sentence-level segmentation + start/end_ms
          ──▶ [3] Translation (LLM/API)       ──▶ bilingual sentence pairs (zh)
          ──▶ [4] Tokenize + lemmatize + POS  ──▶ tappable Token spans + dict_ref
          ──▶ [5] Difficulty labelling        ──▶ difficulty per sentence/video
          ──▶ [6] Build inverted index        ──▶ WordVideoIndex rows
          ──▶ [7] Human review (you) gate      ──▶ approve / correct
          ──▶ [8] Package + publish to CDN     ──▶ LessonPackage (versioned, immutable)
```

- **Step 5 difficulty** is the showcase of "rules → model": V1 = readability heuristics (CEFR word-frequency bands, sentence length, speech rate). V2 = a learned model calibrated by user behaviour (PRD §6.3, §6.6). Same `DifficultyEstimator` interface.
- **Step 7 human-in-the-loop** is deliberate: ASR-then-proofread is the realistic semi-automated workflow (PRD §8 "ASR + 人工校对"). The pipeline emits a review queue; you correct; corrections become labelled data for improving steps 1–5.
- **Idempotent & versioned**: re-running on a video produces a new immutable `LessonPackage` version; the app pins to a version. This is how you avoid "content drift" breaking offline clients.

> Portfolio angle: this DAG is a clean story about *data engineering, weak supervision, and human-in-the-loop labelling* — exactly the day-to-day of an applied MLE.

---

## 7. ML Platform & Data Flywheel — *the spine of the MLE narrative*

Even though models arrive in V2/V3, the **data + eval scaffolding is built early** so that when you train, you can prove it works.

```
 Client events ──▶ event-ingest ──▶ raw event lake (object storage)
                                        │
                                        ▼
                              [Feature build job]  ──▶ Feature Store
                                        │             (user features: clicked word-families,
                                        │              themes, completion rates, level)
                                        ▼
                    ┌───────────── Training pipelines ─────────────┐
                    │ difficulty model · recommender · (eval sets) │
                    └───────────────────┬──────────────────────────┘
                                        ▼
                              Model Registry (versioned)
                                        │
                                        ▼
                        ml-serving  ◀── online features ── Feature Store
                                        │
                                        ▼
                            Predictions logged back ──▶ event lake (closes the loop)
```

Components:
- **Feature Store** (start simple: a Postgres/Parquet table with documented schemas; not a heavyweight vendor system). Offline features for training, a subset materialised for online serving.
- **Model Registry**: versioned artifacts + metadata (training data hash, metrics, date). Even a directory + manifest convention is enough — the *discipline* is what matters.
- **Offline eval harness**: held-out sets and metrics defined *before* shipping a model. For recommendation: offline ranking metrics + online A/B on the **North Star = weekly effective learned sentences** (PRD §4.1). For difficulty: agreement with human labels + behavioural calibration (do "hard"-labelled items actually get more word-taps?).
- **Reproducibility**: every model logs its input data version and config. This is the single most credible thing to show in an MLE interview.

---

## 8. Recommendation (V2.0)

| Stage | Approach | Interface |
|---|---|---|
| **V1 (cold)** | Rules: theme/difficulty filters + recency + popularity | `Recommender.rank(user, candidates)` |
| **V2** | Behavioural model: weight videos by overlap with user's recently clicked word-families & themes; adaptive difficulty from completion + tap-density (PRD §6.6) | *same interface* |

- **Candidate generation** (cheap filter by level/theme) → **ranking** (model) → **business rules** (don't repeat seen, diversity, license filter). Classic two-stage retrieval/ranking — a recognisable, defensible design.
- **Adaptive difficulty** is a feedback controller: high completion + low tap-density → nudge difficulty up; the reverse → down. Implemented against the `DifficultyEstimator` + user level, logged for evaluation.

---

## 9. Conversation & Role-play (V3.0)

```
User ──▶ ml-serving/dialog-orchestrator ──┬─▶ LLM API (Claude) with:
                                          │   - scenario system prompt (e.g. café ordering)
                                          │   - difficulty/level constraint (vocab band, speech rate)
                                          │   - the user's recent vocab as "encourage to use" hints
                                          ▼
                                  Turn + feedback (nativeness, better phrasings)
                                          │
                       Pronunciation-eval SDK (phoneme score) ── for spoken turns
                                          ▼
                              Logged ──▶ event lake (improves difficulty/level models)
```

Design points:
- **The LLM is wrapped, never raw.** A `DialogOrchestrator` enforces level constraints, injects scenario + the user's vocab, and post-processes feedback (PRD §6.7). Difficulty matching is a *prompt + retrieval* problem, with guardrails for cost and reading level.
- **Cost control**: cap turns, cache scenario scaffolding, prefer the latest capable Claude model for quality, and log token usage as an event for cost dashboards.
- **Pronunciation scoring** graduates here from the V1 lightweight scorer to a real phoneme-level SDK, behind the same `PronunciationScorer` protocol defined in §4.2.

---

## 10. Reserved Seams (Ch.13 — designed, not built)

### 10.1 Commercial subscription (Q4)
- `EntitlementService` interface exists now; MVP implementation returns `tier = free` for everyone.
- Feature-gating call sites use `entitlement.can(feature)` rather than hard-coded checks, so introducing tiers later is configuration, not refactoring.
- Data model includes an `Entitlement` table (unused in MVP).
- **Likely future model**: free core loop + paid (advanced AI dialog minutes, unlimited offline downloads, premium content). Nothing built; the architecture simply doesn't preclude it.

### 10.2 Social / check-in sharing (Q3)
- PRD warns this may conflict with the "去打卡化 (de-gamified)" positioning — so it stays **off** by default.
- A `SocialEventBus` (no-op publisher) receives achievement events (e.g. "finished 50 sentences"). When/if social ships, subscribers (feed, share-card generator) attach to the existing event stream — no producer-side changes.

---

## 11. Cross-cutting Concerns

| Concern | Approach |
|---|---|
| **Privacy** (PRD §10) | Recordings processed locally first; only uploaded with explicit consent (needed for V3 scoring). Clear in-app disclosure. Behavioural events anonymised at ingest where possible. |
| **Latency budget** | < 200ms loop interactions met by precomputed packages + on-device caches; network only on the slow path (sync, recommend, dialog). |
| **Offline / weak net** | Content cached as packages; events queued and replayed; graceful degradation (recommend → falls back to rules/popularity). |
| **Accessibility** (PRD §10) | Adjustable subtitle font size; colour-blind-safe highlight palette in `SubtitleRenderer`. |
| **Observability** | Structured logging + the event lake double as product analytics *and* ML training data — one pipeline, two uses. Cost/latency dashboards for LLM + ASR usage. |
| **Content licensing** (PRD §8) | `license_tag` on every `Video`; pipeline refuses to publish unlicensed/unknown-license content. MVP uses self-recorded / public-domain / authorised material only. |

---

## 12. Deployment & Environments

- **MVP**: single small cloud VM or a container platform running the modular monolith + managed Postgres + object storage + CDN. Keep ops trivial; spend complexity budget on ML, not Kubernetes.
- **Content pipeline**: runs as scheduled batch jobs (can start as scripts/cron, graduate to a workflow orchestrator when the DAG grows).
- **ML serving**: lives inside the monolith until it needs independent scaling, then carved out as `ml-serving`.
- **CI**: lint + tests + a content-package schema validation step (a broken package must never reach an offline client).

---

## 13. Roadmap Mapping (architecture ↔ PRD versions)

| Version | New architectural capability | Demonstrates (for interviews) |
|---|---|---|
| **V1.0 MVP** | Reader feature, `LessonPackage` format, content pipeline steps 1–5+7–8, offline-first sync, event ingest | End-to-end product + data engineering; clean scope discipline |
| **V1.5** | `WordVideoIndex` (inverted index), `review-svc` (SM-2/Leitner) | System design: indexing, scheduling algorithms |
| **V2.0** | Feature store, difficulty model, two-stage recommender, eval harness, A/B on North Star | **Core MLE story**: features → model → serving → evaluation |
| **V3.0** | Dialog orchestrator over Claude, phoneme-level scoring | Applied LLM engineering with guardrails + cost control |

---

## 14. Key Risks & Mitigations (architecture view)

| Risk | Architectural mitigation |
|---|---|
| MVP scope creep (PRD §11) | Vertical slices; V1 ships *only* the Reader loop. Reserved seams prevent "while I'm here" feature drift. |
| Offline clients break on content changes | Immutable, versioned `LessonPackage`; clients pin a version. |
| ML can't be evaluated / "looks like magic" | Eval harness + logged inputs from day one; rules-baseline to beat. |
| LLM cost blowup (V3) | Orchestrator caps turns, caches scaffolding, logs token spend. |
| Content/licensing liability | `license_tag` enforced at publish; pipeline gate. |
| Solo-dev velocity vs. "proper" architecture | Modular monolith now, documented seams for later splits — best of both. |

---

## 15. Summary

The architecture is a **content-compilation + offline-first client + progressively-intelligent backend**. It ships *one* polished loop first (Reader), then reuses the same engine and the same data flywheel to add reverse-lookup, spaced repetition, recommendation, and AI dialog. Monetisation and social are pre-wired as inert seams. The deliberate weight on the **content pipeline, feature store, recommender, and evaluation harness** is what turns a personal-use app into a credible MLE portfolio piece for the Australian market.
