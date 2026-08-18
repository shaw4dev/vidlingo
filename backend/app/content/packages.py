"""Move the library between databases as LessonPackage files.

    python -m app.content.packages export --out ../content/packages
    python -m app.content.packages load ../content/packages

Deploying raises a question the code hadn't had to answer: the corpus lives in a
dev SQLite file, and production is an empty Postgres. Re-running ingest against
production would mean re-fetching every caption — slow, and YouTube rate-limits
the caption endpoint by IP, so a fresh box would likely be blocked halfway.

A SQL dump would work but ties the two databases to one engine and one schema
revision. `LessonPackage` is already the project's interchange format — validated,
engine-neutral, diffable — so export rebuilds packages from the tables and `load`
feeds them back through the exact ingestion path used by the pipeline. Round-trip
is stable: sentence ids are `{lesson_id}:{local_id}`, so export strips the prefix
that load puts back.

Clips are *derived* and deliberately not exported — `load_package` regenerates
them, so a re-import picks up the current windowing strategy rather than replaying
an old one. The word index is not derived at load time, so it does travel.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.content.validator import validate_package
from app.db.models import Lesson, Sentence
from app.db.seed import load_package
from app.db.session import SessionLocal

SCHEMA_VERSION = 1


def _local_sentence_id(lesson_id: str, sentence_id: str) -> str:
    prefix = f"{lesson_id}:"
    return sentence_id[len(prefix) :] if sentence_id.startswith(prefix) else sentence_id


def to_package(lesson: Lesson) -> dict:
    """Rebuild the LessonPackage a lesson was ingested from."""
    return {
        "schema_version": SCHEMA_VERSION,
        "package_version": lesson.package_version,
        "video": {
            "id": lesson.id,
            "title": lesson.title,
            "theme": lesson.theme,
            "provider": lesson.provider,
            **({"youtube_id": lesson.youtube_id} if lesson.youtube_id else {}),
            **({"source": lesson.source} if lesson.source else {}),
            "license_tag": lesson.license_tag,
            "duration_ms": lesson.duration_ms,
        },
        "sentences": [
            {
                "id": _local_sentence_id(lesson.id, s.id),
                "idx": s.idx,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "text_en": s.text_en,
                "text_zh": s.text_zh,
                "difficulty": s.difficulty,
                "tokens": [
                    {
                        "char_span": [t.char_start, t.char_end],
                        "surface": t.surface,
                        "lemma": t.lemma,
                        **({"pos": t.pos} if t.pos else {}),
                        **({"dict_ref": t.dict_ref} if t.dict_ref else {}),
                    }
                    for t in sorted(s.tokens, key=lambda t: t.char_start)
                ],
            }
            for s in sorted(lesson.sentences, key=lambda s: s.idx)
        ],
        "index": [
            {
                "lemma": w.lemma,
                "sentence_id": _local_sentence_id(lesson.id, w.sentence_id),
                "start_ms": w.start_ms,
            }
            for w in sorted(lesson.word_index, key=lambda w: (w.start_ms, w.lemma))
        ],
    }


def export(session: Session, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    lessons = session.scalars(
        select(Lesson)
        .options(
            selectinload(Lesson.sentences).selectinload(Sentence.tokens),
            selectinload(Lesson.word_index),
        )
        .order_by(Lesson.id)
    ).all()

    written = 0
    for lesson in lessons:
        package = to_package(lesson)
        # Export must not be able to emit something load would reject.
        errors = validate_package(package)
        if errors:
            print(f"SKIP  {lesson.id}: {'; '.join(errors)}", file=sys.stderr)
            continue
        path = out_dir / f"{lesson.id}.json"
        path.write_text(
            json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written += 1
        print(f"OK    {path.name}  ({len(package['sentences'])} sentences)")

    print(f"\nExported {written} of {len(lessons)} lesson(s) to {out_dir}")
    return 0 if written == len(lessons) else 1


def _package_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        files.extend(sorted(p.glob("*.json")) if p.is_dir() else [p])
    return files


def load(session: Session, paths: list[str]) -> int:
    files = _package_files(paths)
    if not files:
        print("no package files found", file=sys.stderr)
        return 2

    failed = 0
    for path in files:
        try:
            load_package(session, json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError) as exc:
            failed += 1
            print(f"FAIL  {path.name}: {exc}", file=sys.stderr)
            session.rollback()
            continue
        # Commit per package: a bad file late in the run must not undo the
        # good ones before it. Re-running is idempotent (load replaces).
        session.commit()
        print(f"OK    {path.name}")

    print(f"\nLoaded {len(files) - failed} of {len(files)} package(s)")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app.content.packages")
    sub = parser.add_subparsers(dest="cmd", required=True)

    exp = sub.add_parser("export", help="dump every lesson as a LessonPackage file")
    exp.add_argument("--out", default="../content/packages", type=Path)

    ld = sub.add_parser("load", help="ingest package files (or a directory of them)")
    ld.add_argument("paths", nargs="+")

    args = parser.parse_args(argv)
    with SessionLocal() as session:
        return export(session, args.out) if args.cmd == "export" else load(session, args.paths)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
