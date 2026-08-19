"""Wire on-demand word backfill into the word-lookup path.

When a user taps a word that the library barely covers, we kick off
`sourcing.backfill_word` in the background so the word has more fragments *next*
time — the current request still returns immediately with whatever exists now.

The trigger is a FastAPI dependency (`get_backfill_trigger`) so tests can inject
a spy and never touch the network. The default trigger is a no-op unless a
YouTube API key is configured, so word lookup works fine without discovery set up.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from fastapi import BackgroundTasks

from app.config import settings
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

# Occurrences at or above this count are "covered enough" — no backfill fires.
# Kept in sync with backfill_word's own min_coverage (its authoritative re-check).
MIN_COVERAGE = 3


class BackfillTrigger(Protocol):
    def __call__(self, background_tasks: BackgroundTasks, lemma: str) -> None: ...


def _build_translator():
    """Real translation when Anthropic is configured; placeholder otherwise.

    NOTE: without ANTHROPIC_API_KEY, auto-ingested videos carry placeholder zh
    text. Acceptable for a dev/demo library; set the key in prod for real content.
    """
    from app.pipeline.nlp import LLMTranslator, PlaceholderTranslator  # noqa: PLC0415

    return LLMTranslator() if os.getenv("ANTHROPIC_API_KEY") else PlaceholderTranslator()


def _run_backfill(lemma: str) -> None:
    """Best-effort background job: open a fresh session (the request's is closed
    by now) and never let an error crash the worker."""
    from app.pipeline.captions import YouTubeTranscriptFetcher  # noqa: PLC0415
    from app.pipeline.discovery import YouTubeDataAPI  # noqa: PLC0415
    from app.pipeline.sourcing import backfill_word  # noqa: PLC0415

    try:
        api = YouTubeDataAPI(settings.youtube_api_key)
        with SessionLocal() as session:
            report = backfill_word(
                session,
                lemma,
                api,
                YouTubeTranscriptFetcher(),
                _build_translator(),
                min_coverage=MIN_COVERAGE,
            )
            log.info("backfill %s", report.summary)
    except Exception:  # noqa: BLE001 — background best-effort
        log.exception("backfill failed for %r", lemma)


class DefaultBackfillTrigger:
    def __call__(self, background_tasks: BackgroundTasks, lemma: str) -> None:
        if not settings.youtube_api_key:
            return  # discovery not configured — skip silently
        background_tasks.add_task(_run_backfill, lemma)


_default_trigger = DefaultBackfillTrigger()


def get_backfill_trigger() -> BackfillTrigger:
    return _default_trigger
