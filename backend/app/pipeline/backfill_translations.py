"""Translate sentences already in the library (tasks.md T07 follow-up).

    python -m app.pipeline.backfill_translations            # placeholders only
    python -m app.pipeline.backfill_translations --all      # redo everything
    python -m app.pipeline.backfill_translations --lesson yt_abc123

`--translate llm` only applies at ingest, so every lesson pulled in before a
translation key existed carries `（待翻译）` in place of Chinese — which is the
one thing a bilingual reader can't work around. Re-ingesting to fix that would
re-fetch every caption, and YouTube rate-limits captions by IP; the sentences
are already in the database, so translate them there.

Any Anthropic-Messages-compatible endpoint works: set ANTHROPIC_BASE_URL and
TRANSLATE_MODEL (or pass --model) to translate through a different provider.

Batching is per lesson, in `idx` order, because a line of subtitle out of
context is often untranslatable — "Get out." is a different sentence depending
on what preceded it. A batch whose reply doesn't line up is halved and retried
rather than discarded, so one bad line costs a few lines of context, not a
lesson.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Sentence
from app.db.session import SessionLocal
from app.pipeline.nlp import (
    LLMTranslator,
    PlaceholderTranslator,
    TranslationRefused,
    TranslationTruncated,
)

PLACEHOLDER = PlaceholderTranslator.marker


def _pending(session: Session, *, lesson_id: str | None, redo_all: bool) -> list[Sentence]:
    stmt = select(Sentence).order_by(Sentence.lesson_id, Sentence.idx)
    if lesson_id:
        stmt = stmt.where(Sentence.lesson_id == lesson_id)
    if not redo_all:
        stmt = stmt.where(Sentence.text_zh == PLACEHOLDER)
    return list(session.scalars(stmt).all())


def _grouped(sentences: list[Sentence], size: int) -> list[list[Sentence]]:
    """Contiguous runs within one lesson, so each batch reads as a scene."""
    batches: list[list[Sentence]] = []
    current: list[Sentence] = []
    for s in sentences:
        if current and (current[-1].lesson_id != s.lesson_id or len(current) == size):
            batches.append(current)
            current = []
        current.append(s)
    if current:
        batches.append(current)
    return batches


def translate_batch(batch: list[Sentence], translator) -> int:
    """Translate one batch in place; on a misaligned reply, halve and recurse.

    Returns the number of sentences translated. A single line that keeps failing
    is skipped rather than allowed to abort the run — its placeholder stays, and
    a later run will pick it up again.
    """
    try:
        out = translator.translate([s.text_en for s in batch])
    except ValueError:
        if len(batch) == 1:
            print(f"  SKIP {batch[0].id}: unusable reply", file=sys.stderr)
            return 0
        mid = len(batch) // 2
        return translate_batch(batch[:mid], translator) + translate_batch(batch[mid:], translator)

    for sentence, zh in zip(batch, out, strict=True):
        if zh:
            sentence.text_zh = zh
    return len(batch)


def run(
    session: Session,
    translator,
    *,
    lesson_id: str | None = None,
    redo_all: bool = False,
    batch_size: int = 20,
    limit: int | None = None,
) -> int:
    sentences = _pending(session, lesson_id=lesson_id, redo_all=redo_all)
    if limit is not None:
        sentences = sentences[:limit]
    if not sentences:
        print("Nothing to translate.")
        return 0

    batches = _grouped(sentences, batch_size)
    print(f"{len(sentences)} sentence(s) in {len(batches)} batch(es)")

    done = 0
    for i, batch in enumerate(batches, 1):
        try:
            done += translate_batch(batch, translator)
        except TranslationRefused as exc:
            # Says nothing about the other batches — keep going.
            print(f"  REFUSED batch {i} ({exc})", file=sys.stderr)
            continue
        except TranslationTruncated as exc:
            # Splitting wouldn't help — the budget, not the batch, was the
            # problem. Leave the placeholders for a re-run with more headroom.
            print(f"  TRUNCATED batch {i} ({exc})", file=sys.stderr)
            continue
        # Commit per batch: an interrupted run keeps everything it paid for.
        session.commit()
        print(f"  [{i}/{len(batches)}] {batch[0].lesson_id}  +{len(batch)}")

    print(f"\nTranslated {done} of {len(sentences)} sentence(s)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.pipeline.backfill_translations")
    parser.add_argument("--lesson", help="restrict to one lesson id")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="redo_all",
        help="re-translate every sentence, not just the placeholders",
    )
    parser.add_argument("--batch", type=int, default=20, help="sentences per API call")
    parser.add_argument(
        "--model",
        help="model id; defaults to $TRANSLATE_MODEL, else Anthropic's current model",
    )
    parser.add_argument("--limit", type=int, help="stop after N sentences (dry-run sizing)")
    parser.add_argument(
        "--thinking",
        action="store_true",
        help=(
            "let the model think before answering. Off by default: translation "
            "is recall, not reasoning, and reasoning models spend the entire "
            "output budget on it and return nothing"
        ),
    )
    parser.add_argument(
        "--effort",
        default="medium",
        choices=["low", "medium", "high"],
        help=(
            "Anthropic effort level; subtitles rarely need more than medium. "
            "Ignored when ANTHROPIC_BASE_URL points at another provider"
        ),
    )
    args = parser.parse_args(argv)

    import os  # noqa: PLC0415

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2

    translator = LLMTranslator(model=args.model, effort=args.effort, thinking=args.thinking)
    with SessionLocal() as session:
        return run(
            session,
            translator,
            lesson_id=args.lesson,
            redo_all=args.redo_all,
            batch_size=args.batch,
            limit=args.limit,
        )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
