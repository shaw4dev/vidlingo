#!/bin/sh
# Apply DB migrations before serving. Compose already waits for Postgres to be
# healthy (service_healthy), so the DB is reachable by the time this runs.
set -e

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

# Opt-in demo seed (sample lesson + demo user) for a fresh local stack.
if [ "${SEED_ON_START:-0}" = "1" ]; then
    echo "[entrypoint] seeding sample data"
    python -m app.db.seed
fi

echo "[entrypoint] starting: $*"
exec "$@"
