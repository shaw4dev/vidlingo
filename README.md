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

## Status
- **T01 ✅** repo scaffold + CI — backend `/health` builds and is tested.
