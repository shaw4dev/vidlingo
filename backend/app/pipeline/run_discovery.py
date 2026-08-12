"""CLI: source content by discovery instead of hand-collecting IDs.

    # Batch-seed the library from sources:
    python -m app.pipeline.run_discovery seed \
        --playlist PLxxxx:small_talk --channel UCxxxx:interviews \
        --search "english small talk:small_talk" --per-source 25 --translate claude

    # On-demand backfill for one word:
    python -m app.pipeline.run_discovery backfill run --translate claude

Requires YOUTUBE_API_KEY. Exit codes:
    0 ok    1 discovery error    2 usage/config error    3 blocked by YouTube
"""

from __future__ import annotations

import argparse
import sys

from app.config import settings
from app.db.session import SessionLocal
from app.pipeline.captions import YouTubeTranscriptFetcher
from app.pipeline.discovery import (
    ChannelSource,
    DiscoveryError,
    PlaylistSource,
    SearchSource,
    YouTubeDataAPI,
)
from app.pipeline.nlp import ClaudeTranslator, PlaceholderTranslator
from app.pipeline.sourcing import backfill_word, seed_corpus


# ASCII only: this goes to a console that may not be UTF-8 (cp936 on zh-CN
# Windows turns a stray em dash into mojibake).
_BLOCKED_HINT = (
    "\nYouTube blocked our caption requests. This is IP-based rate limiting on the\n"
    "unofficial timedtext endpoint, not a Data API quota issue - your key is fine.\n"
    "Whatever was ingested before the block is committed. To recover:\n"
    "  * wait - blocks typically clear in tens of minutes to a few hours\n"
    "  * re-run the same command; already-ingested videos are skipped\n"
    "  * YouTube caps fetches per window (~30-45), so split large seeds into\n"
    "    several small runs hours apart rather than raising --caption-interval"
)


def _translator(name: str):
    return ClaudeTranslator() if name == "claude" else PlaceholderTranslator()


def _parse_tagged(values: list[str], factory):
    """'ID:theme' or plain 'ID' -> source objects (theme optional)."""
    sources = []
    for v in values or []:
        ref, _, theme = v.partition(":")
        sources.append(factory(ref, theme or None))
    return sources


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.pipeline.run_discovery")
    parser.add_argument("--translate", choices=["placeholder", "claude"], default="placeholder")
    parser.add_argument(
        "--caption-interval",
        type=float,
        default=5.0,
        help="min seconds between caption fetches (default 5.0). Note that YouTube caps "
             "requests per window (~30-45), so spacing softens bursts but won't buy volume; "
             "prefer several small runs hours apart",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed_p = sub.add_parser("seed", help="batch-ingest from sources")
    seed_p.add_argument("--playlist", action="append", metavar="ID[:theme]")
    seed_p.add_argument("--channel", action="append", metavar="ID[:theme]")
    seed_p.add_argument("--search", action="append", metavar="QUERY[:theme]")
    seed_p.add_argument("--per-source", type=int, default=25)

    bf_p = sub.add_parser("backfill", help="ingest videos containing a word")
    bf_p.add_argument("word")
    bf_p.add_argument("--max-ingest", type=int, default=3)
    bf_p.add_argument("--force", action="store_true", help="ignore the searched-words cache")

    args = parser.parse_args(argv)

    if not settings.youtube_api_key:
        print("ERROR: YOUTUBE_API_KEY is not set", file=sys.stderr)
        return 2

    api = YouTubeDataAPI(settings.youtube_api_key)
    fetcher = YouTubeTranscriptFetcher(min_interval_s=args.caption_interval)
    translator = _translator(args.translate)

    try:
        with SessionLocal() as session:
            if args.cmd == "seed":
                sources = [
                    *_parse_tagged(args.playlist, PlaylistSource),
                    *_parse_tagged(args.channel, ChannelSource),
                    *_parse_tagged(args.search, SearchSource),
                ]
                if not sources:
                    print("ERROR: give at least one --playlist/--channel/--search", file=sys.stderr)
                    return 2
                report = seed_corpus(
                    session, sources, api, fetcher, translator, per_source=args.per_source
                )
                print(f"SEED  {report.summary}")
                for vid, err in report.failed:
                    print(f"  FAIL {vid}: {err}", file=sys.stderr)
                if report.blocked:
                    print(_BLOCKED_HINT, file=sys.stderr)
                    return 3
            else:  # backfill
                report = backfill_word(
                    session,
                    args.word,
                    api,
                    fetcher,
                    translator,
                    max_ingest=args.max_ingest,
                    force=args.force,
                )
                print(f"BACKFILL  {report.summary}")
                if report.blocked:
                    print(_BLOCKED_HINT, file=sys.stderr)
                    return 3
    except DiscoveryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
