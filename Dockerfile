# VidLingo — the whole app as one image (tasks.md T10).
#
# Two stages. The first is a Node toolchain that exists only to turn web/ into a
# folder of static files; the second is the Python runtime that actually ships.
# Node, npm and node_modules — several hundred MB — never reach the final image:
# only web/dist is copied across. That's the point of a multi-stage build.
#
# The result is one artifact that runs the same on a laptop and on a host:
#   docker build -t vidlingo .
#   docker run -p 8000:8000 -e DATABASE_URL=... vidlingo
#
# Build context is the repo root, because the build needs both halves of it.

# ---- stage 1: build the client ---------------------------------------------
FROM node:22-slim AS client

WORKDIR /build

# Dependencies first, sources second: npm ci only re-runs when the lockfile
# changes, so editing a component doesn't reinstall the whole tree.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# Same-origin in this image (FastAPI serves these files), so the client's
# default /api base is wrong — point it at the API's own root.
ENV VITE_API_BASE=""
RUN npm run build

# ---- stage 2: the runtime ---------------------------------------------------
# psycopg[binary] ships its own libpq, so slim needs no extra system libs.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static

WORKDIR /app

# Project metadata + source, then a single install (setuptools needs the `app`
# package present to build it, so source must be copied before `pip install .`).
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/samples ./samples
# [llm] pulls in anthropic: the word card's Chinese gloss needs it at
# runtime, and it no-ops without ANTHROPIC_API_KEY.
RUN pip install --upgrade pip && pip install ".[llm]"

COPY --from=client /build/dist ./static

COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Entrypoint applies migrations (and optional seed) before serving.
ENTRYPOINT ["docker-entrypoint.sh"]
# Hosting platforms (Render, Fly, Cloud Run) inject the port to bind as $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
