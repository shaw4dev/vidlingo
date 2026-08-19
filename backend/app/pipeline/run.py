"""CLI: ingest a YouTube video into the content library.

    python -m app.pipeline.run <youtube_id> --title "..." --theme small_talk \
        [--source "Channel"] [--translate placeholder|llm]

Exit codes: 0 ok, 3 no usable captions, 1 other error.
"""

from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.pipeline.captions import NoCaptionsError, YouTubeTranscriptFetcher
from app.pipeline.nlp import LLMTranslator, PlaceholderTranslator
from app.pipeline.pipeline import LessonMeta, ingest_youtube


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.pipeline.run")
    parser.add_argument("youtube_id")
    parser.add_argument("--title", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--source", default=None)
    parser.add_argument("--translate", choices=["placeholder", "llm"], default="placeholder")
    args = parser.parse_args(argv)

    translator = LLMTranslator() if args.translate == "llm" else PlaceholderTranslator()
    meta = LessonMeta(
        youtube_id=args.youtube_id, title=args.title, theme=args.theme, source=args.source
    )

    try:
        with SessionLocal() as session:
            lesson = ingest_youtube(session, meta, YouTubeTranscriptFetcher(), translator)
            n = len(lesson.sentences)
    except NoCaptionsError as exc:
        print(f"SKIP  {args.youtube_id}: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  {args.youtube_id}: {exc}", file=sys.stderr)
        return 1

    print(f"OK    {lesson.id}: {n} sentences ({args.translate} translation)")
    if args.translate == "placeholder":
        print("      note: placeholder zh text — re-run with --translate llm for real content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
