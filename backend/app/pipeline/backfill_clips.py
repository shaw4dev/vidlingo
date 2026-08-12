"""CLI: generate feed clips for lessons that were ingested before clips existed.

New ingests get their clips from `load_package`, so this is only needed for
lessons already in the DB (or after changing the windowing strategy in
`app.pipeline.clips`, when every lesson's clips should be re-planned).

    # Lessons that currently have no clips:
    python -m app.pipeline.backfill_clips

    # Re-plan every lesson (after a strategy change):
    python -m app.pipeline.backfill_clips --all

Idempotent either way — `generate_clips` replaces a lesson's existing clips.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Lesson
from app.db.session import SessionLocal
from app.pipeline.clips import SentenceSpan, generate_clips


def backfill_clips(session: Session, *, regenerate_all: bool = False) -> dict[str, int]:
    """Plan and persist clips for lessons. Returns {lesson_id: clip_count}."""
    stmt = select(Lesson).options(
        selectinload(Lesson.sentences), selectinload(Lesson.clips)
    )
    counts: dict[str, int] = {}
    for lesson in session.execute(stmt).scalars():
        if lesson.clips and not regenerate_all:
            continue
        spans = [
            SentenceSpan(
                idx=s.idx,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text_en=s.text_en,
                difficulty=s.difficulty,
            )
            for s in lesson.sentences
        ]
        counts[lesson.id] = len(generate_clips(session, lesson, spans))
    session.commit()
    return counts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.pipeline.backfill_clips")
    parser.add_argument(
        "--all",
        dest="regenerate_all",
        action="store_true",
        help="re-plan clips for every lesson, not just ones without any",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        counts = backfill_clips(session, regenerate_all=args.regenerate_all)

    for lesson_id, n in counts.items():
        print(f"  {lesson_id}: {n} clip(s)")
    print(f"CLIPS  lessons={len(counts)} clips={sum(counts.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
