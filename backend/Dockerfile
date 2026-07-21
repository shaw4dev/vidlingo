# VidLingo backend image (architecture.md §12 — modular monolith).
# psycopg[binary] ships its own libpq, so slim needs no extra system libs.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Project metadata + source, then a single install (setuptools needs the `app`
# package present to build it, so source must be copied before `pip install .`).
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY samples ./samples
RUN pip install --upgrade pip && pip install .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Entrypoint applies migrations (and optional seed) before serving.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
