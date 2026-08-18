"""Remove lessons from the library (curation, not migration).

    python -m app.db.remove_lesson yt_dQw4w9WgXcQ vid_smalltalk_001

Ingest is automatic, so pruning has to be too: a placeholder, a wrong-language
clip or a video whose captions turned out to be junk needs a way out. Deleting
through the ORM (not raw SQL) is deliberate — SQLite ignores FK cascades unless
`PRAGMA foreign_keys` is on, and `session.delete()` follows the relationships,
which is what actually clears sentences, tokens, clips and word_index.
"""

from __future__ import annotations

import sys

from sqlalchemy import select, update

from app.db.models import Lesson, Sentence, VocabItem
from app.db.session import SessionLocal


def remove(session, lesson_id: str) -> bool:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        return False
    # A saved word points at the sentence she met it in. The FK is SET NULL, but
    # SQLite won't enforce it, so detach explicitly and keep her vocab entry.
    sentence_ids = session.scalars(
        select(Sentence.id).where(Sentence.lesson_id == lesson_id)
    ).all()
    if sentence_ids:
        session.execute(
            update(VocabItem)
            .where(VocabItem.source_sentence_id.in_(sentence_ids))
            .values(source_sentence_id=None)
        )
    session.delete(lesson)
    return True


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m app.db.remove_lesson <lesson_id> [...]", file=sys.stderr)
        return 2
    with SessionLocal() as session:
        for lesson_id in argv:
            print(f"{'removed' if remove(session, lesson_id) else 'not found'}  {lesson_id}")
        session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
