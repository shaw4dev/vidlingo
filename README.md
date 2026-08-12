# VidLingo

Video English-learning app — learn by watching real video + sentence-level close
reading. See [`PRD_v1.md`](PRD_v1.md), [`architecture.md`](architecture.md), and
[`tasks.md`](tasks.md).

## Repo layout
```
backend/   FastAPI modular monolith (architecture.md §5)
web/        React + Vite + TS app — the client (architecture.md §4, ADR-002); scaffolded in T11
ios/        (parked) native iOS is backlog per ADR-002 — kept as a placeholder, not built for MVP
.github/    CI workflows
```

## Backend — quick start
```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
#                       source .venv/bin/activate        # macOS/Linux
pip install -e ".[dev]"

uvicorn app.main:app --reload    # serve → http://127.0.0.1:8000/health
ruff check .                     # lint
pytest                           # test
```

## CI
`.github/workflows/ci.yml` runs on push to `main` and PRs:
- **backend**: ruff lint → pytest → import/build check.
- **ios-build**: builds the Xcode project on a macOS runner once it exists (skips until then).

## Content packages
A `LessonPackage` is the compiled, immutable learning unit (architecture.md §6).
Schema: `backend/app/content/schema/lesson_package.schema.json`. Validate files:
```bash
cd backend
python -m app.content.validate samples/lesson_package.sample.json
```

## Database
SQLAlchemy 2.0 models + Alembic migrations (architecture.md §5.2). Defaults to a
local SQLite file (`DATABASE_URL`); Postgres in Docker/AWS later.
```bash
cd backend
alembic upgrade head        # create tables
python -m app.db.seed       # load the sample lesson + demo user
```

## Content sourcing (discovery + auto-backfill)
The library is built by pointing at sources, not by collecting video IDs by hand
(tasks.md T17). Needs a YouTube Data API v3 key in `YOUTUBE_API_KEY`; add
`ANTHROPIC_API_KEY` for real translations (otherwise placeholder zh text).
```bash
cd backend
# Batch-seed from playlists / channels / searches ("ID:theme" tags the lessons):
python -m app.pipeline.run_discovery seed \
    --playlist PLxxxx:small_talk --channel UCxxxx:interviews \
    --search "english cafe ordering:cafe" --per-source 25 --translate claude

# Ingest videos whose captions actually contain one word:
python -m app.pipeline.run_discovery backfill run --translate claude

# Feed clips for lessons ingested before clips existed (--all re-plans every lesson):
python -m app.pipeline.backfill_clips
```
Word lookup also self-heals: `GET /words/{lemma}/occurrences` schedules a
background backfill when a word has fewer than 3 occurrences, so it has more
examples next visit. Quota is guarded (search = 100 of ~10k daily units): covered
words never search, and each lemma is searched at most once (`word_searches`).
Without `YOUTUBE_API_KEY` everything above no-ops and the app runs normally.

## Web app (client)
React + Vite + TypeScript SPA (`web/`), consuming the backend REST API (ADR-002).
```bash
cd web
npm install
npm run dev          # → http://localhost:5173  (dev-proxies /api → :8000)
npm run build        # type-check + production build
```
Run the backend (above) on `:8000` first; the Vite dev server proxies `/api/*`
to it, so no CORS setup is needed. Override the API base with `VITE_API_BASE`.

## Docker (local stack)
Run the API + Postgres together (architecture.md §12). Requires Docker Desktop.
```bash
cp .env.example .env             # optional: adjust creds / SECRET_KEY
docker compose up --build        # API → http://localhost:8000/health
SEED_ON_START=1 docker compose up --build   # also load the demo lesson + user
```
The API container applies Alembic migrations on start (`backend/docker-entrypoint.sh`),
then serves uvicorn. Postgres data persists in the `pgdata` volume.

## Status
- **T01 ✅** repo scaffold + CI — backend `/health` builds and is tested.
- **T02 ✅** `LessonPackage` schema + validator (structure + semantic checks); CI validates the sample.
- **T03 ✅** Postgres data model + Alembic migrations (lessons/sentences/tokens/word_index/users/vocab); `load_package` ingests validated packages; CI runs migrate+seed.
- **T04 ✅** Auth: register/login/me with JWT bearer tokens + PBKDF2 password hashing; `get_current_user` dependency for protected routes.
- **T05 ✅** Content API: `GET /lessons` (theme/difficulty filters), `GET /lessons/{id}` (full package w/ sentences+tokens), `GET /words/{lemma}/occurrences` (reverse lookup).
- **T06 ✅** Vocab API (auth'd, per-user): `POST/GET/PATCH/DELETE /vocab`; responses embed the source sentence for jump-back. **Phase A backend complete.**
- **T07 ✅** Content pipeline: `youtube_id` → captions → segment → tokenize/lemmatize → build+validate `LessonPackage` → load to DB. Pluggable providers; placeholder vs. Claude translation. CLI: `python -m app.pipeline.run <id> --title ... --theme ...`.
- **T09 ✅** Dockerized: `backend/Dockerfile` (non-root, migrates on start) + root `docker-compose.yml` (API + Postgres 16, healthcheck-gated). `docker compose up --build` serves the API on a real Postgres. (T08 ingest deferred — needs video curation + a translation key.)
- **T11 ✅** Web app scaffold (`web/`, React+Vite+TS): routing, typed API client, register/login + authenticated `/auth/me`, protected routes, lesson browse. Verified end-to-end through the dev proxy against the live backend.
- **T12 ✅** Reader: YouTube IFrame player driven by sentence timestamps (play/pause, prev/next, single-sentence loop, auto-pause, 0.5–1.5× speed), tappable bilingual subtitles with 中英/仅英/仅中/关闭 modes + click-to-jump transcript. Build+lint clean; visual acceptance best with real content (T08).
- **T13 ✅** Word card: tap any word for phonetic, audio, POS + senses, a Chinese gloss and the in-context meaning, plus add-to-vocab and reverse lookup. Definitions come from a free keyless dictionary composed with an optional Claude gloss (no free source has both), cached in `dictionary_entries` — one network call per lemma, ever. Client caches in memory + localStorage, 404s included.
- **T16 ✅** Feed clips: `clips` table + swappable 30–90s windowing strategy, generated at ingest; `GET /feed` (theme/difficulty filters, offset paging, lesson-interleaving order). `backfill_clips` CLI for pre-existing lessons.
- **T17 ✅** Content discovery + auto-sourcing: YouTube Data API v3 client with playlist/channel/search sources; `seed_corpus` batch ingest; `backfill_word` ingests only videos whose captions truly contain the lemma; quota guarded by a coverage check + `word_searches` cache. Wired into word lookup as a non-blocking background task; word lookup now lemmatizes its input.
- **T18 ✅** Web feed + word detail: `/` is a vertical snap-scroll clip feed (only the visible clip mounts a player, looping its window; thumbnails elsewhere; next page prefetched), every caption word links to `/word/:word`, which browses that lemma's real-video fragments with jump-into-Reader. Old lesson list moved to `/browse`. Build+lint clean.
