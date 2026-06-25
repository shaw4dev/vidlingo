# VidLingo

Video English-learning app — learn by watching real video + sentence-level close
reading. See [`PRD_v1.md`](PRD_v1.md), [`architecture.md`](architecture.md), and
[`tasks.md`](tasks.md).

## Repo layout
```
backend/   FastAPI modular monolith (architecture.md §5)
ios/        SwiftUI app — placeholder until generated on macOS (architecture.md §4)
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

## Status
- **T01 ✅** repo scaffold + CI — backend `/health` builds and is tested.
- **T02 ✅** `LessonPackage` schema + validator (structure + semantic checks); CI validates the sample.
- **T03 ✅** Postgres data model + Alembic migrations (lessons/sentences/tokens/word_index/users/vocab); `load_package` ingests validated packages; CI runs migrate+seed.
- **T04 ✅** Auth: register/login/me with JWT bearer tokens + PBKDF2 password hashing; `get_current_user` dependency for protected routes.
