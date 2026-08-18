"""T10: exporting the library as LessonPackages and loading it back.

This is how the corpus reaches a production database, so the property that
matters is round-trip fidelity: export -> load must reproduce the same rows, or
the deployed app quietly differs from the one that was tested.
"""

import json

from app.content.packages import export, load, to_package
from app.content.validator import validate_package
from app.db.models import Clip, Lesson, Sentence, Token, WordIndex
from app.db.seed import load_package


def _package(lesson_id: str = "pkg_test") -> dict:
    return {
        "schema_version": 1,
        "package_version": 1,
        "video": {
            "id": lesson_id,
            "title": "Ordering coffee",
            "theme": "small_talk",
            "provider": "youtube",
            "youtube_id": "abcdefghijk",
            "source": "Test Channel",
            "license_tag": "youtube_embed",
            "duration_ms": 8000,
        },
        "sentences": [
            {
                "id": "s1",
                "idx": 0,
                "start_ms": 0,
                "end_ms": 4000,
                "text_en": "I run every morning.",
                "text_zh": "我每天早上跑步。",
                "difficulty": "easy",
                "tokens": [
                    {"char_span": [2, 5], "surface": "run", "lemma": "run", "pos": "VERB"},
                    {"char_span": [12, 19], "surface": "morning", "lemma": "morning"},
                ],
            },
            {
                "id": "s2",
                "idx": 1,
                "start_ms": 4000,
                "end_ms": 8000,
                "text_en": "She runs faster.",
                "text_zh": "她跑得更快。",
                "difficulty": "medium",
                "tokens": [
                    {"char_span": [4, 8], "surface": "runs", "lemma": "run"},
                ],
            },
        ],
        "index": [
            {"lemma": "run", "sentence_id": "s1", "start_ms": 0},
            {"lemma": "morning", "sentence_id": "s1", "start_ms": 0},
            {"lemma": "run", "sentence_id": "s2", "start_ms": 4000},
        ],
    }


def _snapshot(db) -> dict:
    """Everything a package is supposed to carry, in a comparable shape."""
    return {
        "lessons": sorted(
            (le.id, le.title, le.theme, le.youtube_id, le.duration_ms, le.difficulty)
            for le in db.query(Lesson).all()
        ),
        "sentences": sorted(
            (s.id, s.idx, s.start_ms, s.end_ms, s.text_en, s.text_zh, s.difficulty)
            for s in db.query(Sentence).all()
        ),
        "tokens": sorted(
            (t.sentence_id, t.char_start, t.char_end, t.surface, t.lemma, t.pos)
            for t in db.query(Token).all()
        ),
        "word_index": sorted(
            (w.lemma, w.sentence_id, w.lesson_id, w.start_ms)
            for w in db.query(WordIndex).all()
        ),
        "clips": sorted(
            (c.lesson_id, c.start_ms, c.end_ms, c.difficulty)
            for c in db.query(Clip).all()
        ),
    }


def test_export_then_load_reproduces_every_row(db, tmp_path):
    load_package(db, _package())
    db.commit()
    before = _snapshot(db)

    assert export(db, tmp_path) == 0
    assert (tmp_path / "pkg_test.json").exists()

    # Wipe the library and rebuild it from the files alone.
    for lesson in db.query(Lesson).all():
        db.delete(lesson)
    db.commit()
    assert _snapshot(db)["lessons"] == []

    assert load(db, [str(tmp_path)]) == 0
    assert _snapshot(db) == before


def test_exported_sentence_ids_are_local_not_global(db, tmp_path):
    """Load prefixes sentence ids with the lesson id. Exporting them prefixed
    would double the prefix on the next round trip."""
    load_package(db, _package())
    db.commit()
    export(db, tmp_path)

    package = json.loads((tmp_path / "pkg_test.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in package["sentences"]] == ["s1", "s2"]
    assert {row["sentence_id"] for row in package["index"]} == {"s1", "s2"}


def test_export_round_trips_through_the_validator(db, tmp_path):
    """Whatever export writes must be loadable, so it is validated on the way
    out rather than failing on the way in, on the production box."""
    load_package(db, _package())
    db.commit()

    lesson = db.get(Lesson, "pkg_test")
    assert validate_package(to_package(lesson)) == []


def test_load_reports_a_bad_file_without_losing_the_good_ones(db, tmp_path):
    (tmp_path / "a_good.json").write_text(
        json.dumps(_package("pkg_good")), encoding="utf-8"
    )
    (tmp_path / "b_bad.json").write_text(
        json.dumps({"schema_version": 1, "package_version": 1}), encoding="utf-8"
    )

    assert load(db, [str(tmp_path)]) == 1
    assert db.get(Lesson, "pkg_good") is not None
