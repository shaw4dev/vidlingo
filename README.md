# VidLingo

Learn English from real video. Watch a clip, step through it sentence by
sentence, tap any word for a definition — then see that same word used in other
real videos, at the timestamp it was spoken.

**FastAPI · PostgreSQL · React + TypeScript · Docker**

Three things shaped the engineering more than the feature list did:

- **The library builds itself.** You point the sourcing job at YouTube
  playlists or channels rather than collecting video IDs by hand. It discovers
  videos, fetches captions, segments them into sentences, tokenizes and
  lemmatizes, then compiles an immutable `LessonPackage` that is
  schema-validated before it may touch the database.
- **Reverse lookup is the product.** Every lemma is indexed back to the exact
  sentence and timestamp it came from, so a word card shows real usage instead
  of a dictionary example. A word with too few occurrences triggers a
  background job that goes and finds more.
- **Real-world data and third-party limits are the hard part.** Broadcast
  captions aren't clean text; YouTube's search endpoint costs 100 of 10,000
  daily quota units and its caption endpoint is IP-policed. Both are handled
  explicitly rather than hoped away — see
  [Design notes](#design-notes-the-non-obvious-parts) below.

**Status:** functional end to end against a live library of 39 ingested videos
(Friends, The Office, TED, late-night). It ships as a single Docker image
containing both halves, so `docker compose up` gives you the whole app on
Postgres. Hosted demo pending. Design docs: [`PRD_v1.md`](PRD_v1.md),
[`architecture.md`](architecture.md), [`tasks.md`](tasks.md).

## Repo layout
```
backend/     FastAPI modular monolith (architecture.md §5)
web/         React + Vite + TS client (architecture.md §4, ADR-002)
Dockerfile   multi-stage: builds web/, serves it and the API from one image
ios/         (parked) native iOS is backlog per ADR-002 — placeholder, not built for MVP
.github/     CI workflows
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
- **backend**: ruff → pytest → package validation → migrate+seed → import check.
- **web**: oxlint → `tsc -b` → production build.
- **image**: builds the Docker image, runs the container, and checks it actually
  answers — `/health`, a real API response, and a client-only deep link. The
  image is the deployable artifact, so "it builds" isn't the interesting claim.

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
    --search "english cafe ordering:cafe" --per-source 25 --translate llm

# Ingest videos whose captions actually contain one word:
python -m app.pipeline.run_discovery backfill run --translate llm

# Feed clips for lessons ingested before clips existed (--all re-plans every lesson):
python -m app.pipeline.backfill_clips

# Translate sentences already in the library (see Translation below):
python -m app.pipeline.backfill_translations
```
Candidates are screened before any caption is fetched (`videos.list`, 1 unit per
50 ids): a video that forbids embedding is a blank IFrame, and a channel's
40-minute "best of season 5" compilation makes one lesson nobody finishes, so
`--min-duration`/`--max-duration` bound what counts as a lesson. That screen is
worth its quota because caption fetches — not API units — are the scarce
resource.
Word lookup also self-heals: `GET /words/{lemma}/occurrences` schedules a
background backfill when a word has fewer than 3 occurrences, so it has more
examples next visit. Quota is guarded (search = 100 of ~10k daily units): covered
words never search, and each lemma is searched at most once (`word_searches`).
Without `YOUTUBE_API_KEY` everything above no-ops and the app runs normally.

## Translation
Chinese subtitles come from any endpoint that speaks the Anthropic Messages
API. It defaults to Anthropic; two environment variables redirect it at another
provider without touching code:
```bash
ANTHROPIC_API_KEY=...                              # required either way
ANTHROPIC_BASE_URL=https://<gateway>/anthropic     # omit to use Anthropic
TRANSLATE_MODEL=<that provider's model id>         # or pass --model
```
`--effort` is an Anthropic-only parameter and is dropped automatically when
`ANTHROPIC_BASE_URL` is set, because a gateway that merely speaks the wire
format will reject the unknown field. `anthropic` is an optional extra
(`pip install -e ".[llm]"`); without it, and without a key, translation falls
back to a placeholder and everything else still runs.

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

## Docker — the whole app in one container
The root `Dockerfile` is multi-stage: a Node stage turns `web/` into static
files and is then discarded, so `node_modules` never reaches the shipped image;
the Python stage serves those files *and* the API from one process. That's the
same image in development and in production — deployment runs the container,
nothing more.
```bash
cp .env.example .env             # optional: adjust creds / SECRET_KEY
docker compose up --build        # whole app → http://localhost:8000
SEED_ON_START=1 docker compose up --build   # also load the demo lesson + user

docker build -t vidlingo .       # or just the image, no compose
docker run -p 8000:8000 -e DATABASE_URL=... vidlingo
```
Compose runs it against Postgres 16 (healthcheck-gated), so it rehearses
production rather than a different arrangement of the same parts. The container
applies Alembic migrations on start (`backend/docker-entrypoint.sh`); Postgres
data persists in the `pgdata` volume.

## Deployment
`render.yaml` is a Render Blueprint declaring one Docker service. The database
is deliberately *not* declared there: Render deletes free Postgres instances
after 30 days, so `DATABASE_URL` points at an external managed Postgres instead
— one environment variable to change providers.

Moving the library into a fresh database is its own problem: re-running ingest
there would re-fetch every caption, and YouTube rate-limits that endpoint by IP.
`LessonPackage` is already the interchange format, so the corpus travels as
validated JSON through the same ingestion path the pipeline uses:
```bash
cd backend
python -m app.content.packages export --out ../content/packages   # from dev
DATABASE_URL=<production> python -m app.content.packages load ../content/packages
```
The round trip is exact and tested — same rows, same ids. Clips are regenerated
rather than exported, so a re-import picks up the current windowing strategy.
Pruning is the other half of automatic ingest:
```bash
python -m app.db.remove_lesson yt_<id> [...]
```

## Design notes: the non-obvious parts

**Captions are not clean text.** Auditing the first 21 ingested lessons found
that 69.5% of sentences carried a speaker dash (`-Yeah. -Oh.`), 9.1% a sound tag
(`[ Engine revs ]`) and 3.8% music marks. Every token is indexed, so `[APPLAUSE]`
had become a vocabulary word. The cleaner strips all three; the delicate case is
the dash, which must vanish as a speaker marker while surviving as a real hyphen
— it is only removed at a word boundary hugging the next token, leaving `I-I'm`,
`ex-husband`, `M-O-R-R-I-S` and the em dash `this -- this` intact.

**Two failure modes that look alike but aren't.** A video with no usable
captions means *skip this one*. A rate-limit block means *stop the batch* — it
says nothing about the video, and the next request will fail identically, so
retrying only deepens the block. They are separate exception types with separate
exit codes. The block path also deliberately writes no cache row: recording a
search that never actually ran would skip that word forever.

**Quota is a first-class constraint.** `search` costs 100 of 10,000 daily units
while `playlistItems` costs 1, so sourcing prefers playlists, skips words the
library already covers, and remembers fruitless searches in `word_searches`.
Dictionary lookups compose a free keyless provider with an optional LLM gloss
(no free source has both) and cache into `dictionary_entries` — one network call
per lemma, ever.

**A bug the dev database was hiding.** `load_package` re-ingests a lesson by
deleting and reinserting it, but `word_index` had only a database-level
`ondelete="CASCADE"` and no ORM relationship — and `session.delete()` follows
relationships, while SQLite ignores foreign keys entirely unless
`PRAGMA foreign_keys` is on. Stale rows survived re-ingest, and because sentence
IDs are derived from the lesson ID they still pointed at live sentences: not
orphans, just silent duplicates inflating every reverse lookup. Postgres would
have cascaded correctly, which is exactly why it hid in development. Fixed at
both levels and pinned with a regression test.

## Status
- **T01 ✅** repo scaffold + CI — backend `/health` builds and is tested.
- **T02 ✅** `LessonPackage` schema + validator (structure + semantic checks); CI validates the sample.
- **T03 ✅** Postgres data model + Alembic migrations (lessons/sentences/tokens/word_index/users/vocab); `load_package` ingests validated packages; CI runs migrate+seed.
- **T04 ✅** Auth: register/login/me with JWT bearer tokens + PBKDF2 password hashing; `get_current_user` dependency for protected routes.
- **T05 ✅** Content API: `GET /lessons` (theme/difficulty filters), `GET /lessons/{id}` (full package w/ sentences+tokens), `GET /words/{lemma}/occurrences` (reverse lookup).
- **T06 ✅** Vocab API (auth'd, per-user): `POST/GET/PATCH/DELETE /vocab`; responses embed the source sentence for jump-back. **Phase A backend complete.**
- **T07 ✅** Content pipeline: `youtube_id` → captions → segment → tokenize/lemmatize → build+validate `LessonPackage` → load to DB. Pluggable providers; placeholder vs. real LLM translation. CLI: `python -m app.pipeline.run <id> --title ... --theme ...`.
- **T09 ✅** Dockerized: `backend/Dockerfile` (non-root, migrates on start) + root `docker-compose.yml` (API + Postgres 16, healthcheck-gated). `docker compose up --build` serves the API on a real Postgres. (T08 ingest deferred — needs video curation + a translation key.)
- **T11 ✅** Web app scaffold (`web/`, React+Vite+TS): routing, typed API client, register/login + authenticated `/auth/me`, protected routes, lesson browse. Verified end-to-end through the dev proxy against the live backend.
- **T12 ✅** Reader: YouTube IFrame player driven by sentence timestamps (play/pause, prev/next, single-sentence loop, auto-pause, 0.5–1.5× speed), tappable bilingual subtitles with 中英/仅英/仅中/关闭 modes + click-to-jump transcript. Build+lint clean; visual acceptance best with real content (T08).
- **T13 ✅** Word card: tap any word for phonetic, audio, POS + senses, a Chinese gloss and the in-context meaning, plus add-to-vocab and reverse lookup. Definitions come from a free keyless dictionary composed with an optional Claude gloss (no free source has both), cached in `dictionary_entries` — one network call per lemma, ever. Client caches in memory + localStorage, 404s included.
- **T16 ✅** Feed clips: `clips` table + swappable 30–90s windowing strategy, generated at ingest; `GET /feed` (theme/difficulty filters, offset paging, lesson-interleaving order). `backfill_clips` CLI for pre-existing lessons.
- **T17 ✅** Content discovery + auto-sourcing: YouTube Data API v3 client with playlist/channel/search sources; `seed_corpus` batch ingest; `backfill_word` ingests only videos whose captions truly contain the lemma; quota guarded by a coverage check + `word_searches` cache. Wired into word lookup as a non-blocking background task; word lookup now lemmatizes its input.
- **T10 🔨** Deployment: multi-stage image (Node build stage discarded; FastAPI serves the built client with an SPA deep-link fallback), `render.yaml` blueprint, CORS behind an env var, and `app.content.packages` to move the corpus into a fresh database as validated LessonPackages. CI builds the image and smoke-tests the running container. Hosting pending.
- **T18 ✅** Web feed + word detail: `/` is a vertical snap-scroll clip feed (only the visible clip mounts a player, looping its window; thumbnails elsewhere; next page prefetched), every caption word links to `/word/:word`, which browses that lemma's real-video fragments with jump-into-Reader. Old lesson list moved to `/browse`. Build+lint clean.
