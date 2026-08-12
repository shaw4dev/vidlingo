"""Load a validated LessonPackage into the DB, and seed initial data.

`load_package` is the single ingestion path reused by the seed script now and by
the content pipeline later (T07). It validates first (T02) so malformed content
never reaches the database.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.validator import validate_package
from app.db.models import Lesson, Sentence, Token, User, WordIndex
from app.pipeline.clips import SentenceSpan, generate_clips

BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLE_PACKAGE = BACKEND_DIR / "samples" / "lesson_package.sample.json"


def _global_sentence_id(lesson_id: str, local_id: str) -> str:
    return f"{lesson_id}:{local_id}"


def load_package(session: Session, package: dict) -> Lesson:
    """Insert (or replace) a LessonPackage. Raises ValueError if invalid."""
    errors = validate_package(package)
    if errors:
        raise ValueError("invalid LessonPackage:\n  " + "\n  ".join(errors))

    v = package["video"]
    lesson_id = v["id"]

    # Idempotent: replace an existing lesson (cascade clears its children).
    existing = session.get(Lesson, lesson_id)
    if existing is not None:
        session.delete(existing)
        session.flush()

    sentence_difficulties = [s["difficulty"] for s in package["sentences"]]
    lesson = Lesson(
        id=lesson_id,
        provider=v["provider"],
        youtube_id=v.get("youtube_id"),
        title=v["title"],
        theme=v["theme"],
        source=v.get("source"),
        license_tag=v["license_tag"],
        duration_ms=v["duration_ms"],
        difficulty=_dominant(sentence_difficulties),
        schema_version=package["schema_version"],
        package_version=package["package_version"],
    )
    session.add(lesson)

    local_to_global: dict[str, str] = {}
    for s in package["sentences"]:
        gid = _global_sentence_id(lesson_id, s["id"])
        local_to_global[s["id"]] = gid
        sentence = Sentence(
            id=gid,
            lesson_id=lesson_id,
            idx=s["idx"],
            start_ms=s["start_ms"],
            end_ms=s["end_ms"],
            text_en=s["text_en"],
            text_zh=s["text_zh"],
            difficulty=s["difficulty"],
        )
        session.add(sentence)
        for t in s["tokens"]:
            start, end = t["char_span"]
            session.add(
                Token(
                    sentence_id=gid,
                    char_start=start,
                    char_end=end,
                    surface=t["surface"],
                    lemma=t["lemma"],
                    pos=t.get("pos"),
                    dict_ref=t.get("dict_ref"),
                )
            )

    for row in package.get("index", []):
        gid = local_to_global.get(row["sentence_id"])
        if gid is None:
            continue  # validator already guarantees this won't happen
        session.add(
            WordIndex(
                lemma=row["lemma"],
                sentence_id=gid,
                lesson_id=lesson_id,
                start_ms=row["start_ms"],
            )
        )

    session.flush()

    spans = [
        SentenceSpan(
            idx=s["idx"],
            start_ms=s["start_ms"],
            end_ms=s["end_ms"],
            text_en=s["text_en"],
            difficulty=s["difficulty"],
        )
        for s in package["sentences"]
    ]
    generate_clips(session, lesson, spans)

    session.flush()
    return lesson


def _dominant(difficulties: list[str]) -> str:
    """Lesson-level difficulty = the hardest sentence difficulty present."""
    order = {"easy": 0, "medium": 1, "hard": 2}
    return max(difficulties, key=lambda d: order.get(d, 0)) if difficulties else "easy"


def ensure_demo_user(session: Session) -> User:
    user = session.scalars(select(User).where(User.username == "demo")).first()
    if user is None:
        user = User(username="demo")
        session.add(user)
        session.flush()
    return user


def seed_initial(session: Session) -> None:
    """Load the sample lesson and a demo user. Idempotent."""
    ensure_demo_user(session)
    package = json.loads(SAMPLE_PACKAGE.read_text(encoding="utf-8"))
    load_package(session, package)
    session.commit()


if __name__ == "__main__":
    from app.db.session import SessionLocal

    with SessionLocal() as s:
        seed_initial(s)
        print("Seeded sample lesson + demo user.")
