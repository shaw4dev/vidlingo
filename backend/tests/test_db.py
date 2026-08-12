import json

import pytest
from sqlalchemy import func, select

from app.db.models import Lesson, Sentence, Token, VocabItem, WordIndex
from app.db.seed import SAMPLE_PACKAGE, ensure_demo_user, load_package, seed_initial


def _sample() -> dict:
    return json.loads(SAMPLE_PACKAGE.read_text(encoding="utf-8"))


def test_seed_loads_sample(db):
    seed_initial(db)
    assert db.scalar(select(func.count()).select_from(Lesson)) == 1
    assert db.scalar(select(func.count()).select_from(Sentence)) == 2
    assert db.scalar(select(func.count()).select_from(Token)) == 6


def test_reverse_lookup_by_lemma(db):
    seed_initial(db)
    rows = db.scalars(select(WordIndex).where(WordIndex.lemma == "go")).all()
    assert len(rows) == 1
    assert rows[0].lesson_id == "vid_smalltalk_001"
    assert rows[0].sentence_id == "vid_smalltalk_001:s1"


def test_global_sentence_ids_namespaced_by_lesson(db):
    pkg = _sample()
    load_package(db, pkg)
    pkg2 = _sample()
    pkg2["video"]["id"] = "other_lesson"
    pkg2["video"]["youtube_id"] = "abcdefghij1"
    load_package(db, pkg2)
    ids = set(db.scalars(select(Sentence.id)).all())
    assert "vid_smalltalk_001:s1" in ids
    assert "other_lesson:s1" in ids  # same local id, no collision


def test_load_package_is_idempotent(db):
    load_package(db, _sample())
    load_package(db, _sample())  # re-load same lesson
    assert db.scalar(select(func.count()).select_from(Lesson)) == 1
    assert db.scalar(select(func.count()).select_from(Sentence)) == 2


def test_reload_replaces_word_index_instead_of_duplicating(db):
    """Every child table must be cleared on re-ingest, not just sentences.

    word_index is the one that hides a leak: sentence ids are derived from the
    lesson id, so stale rows still point at live sentences and read as valid
    duplicates rather than orphans — silently doubling every reverse lookup.
    """
    load_package(db, _sample())
    before_index = db.scalar(select(func.count()).select_from(WordIndex))
    before_tokens = db.scalar(select(func.count()).select_from(Token))
    assert before_index > 0

    load_package(db, _sample())

    assert db.scalar(select(func.count()).select_from(WordIndex)) == before_index
    assert db.scalar(select(func.count()).select_from(Token)) == before_tokens


def test_load_package_rejects_invalid(db):
    bad = _sample()
    bad["sentences"][0]["end_ms"] = 999999  # exceeds duration -> semantic error
    with pytest.raises(ValueError, match="invalid LessonPackage"):
        load_package(db, bad)


def test_vocab_unique_per_user(db):
    seed_initial(db)
    user = ensure_demo_user(db)
    db.add(VocabItem(user_id=user.id, lemma="go", surface="going"))
    db.commit()
    stored = db.scalars(select(VocabItem).where(VocabItem.user_id == user.id)).all()
    assert [v.lemma for v in stored] == ["go"]
