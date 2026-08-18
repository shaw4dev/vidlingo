"""Translating sentences already in the library, offline.

The translator is a fake throughout — the point of these tests is the batching
and failure handling around it, which is where a bulk job either preserves work
or throws it away.
"""

import pytest

from app.db.models import Sentence
from app.pipeline.backfill_translations import PLACEHOLDER, _grouped, run, translate_batch
from app.pipeline.nlp import TranslationRefused


class FakeTranslator:
    """Echoes a marker per line. `misaligned` names batch sizes it answers badly."""

    def __init__(self, *, misaligned: set[int] | None = None, refuse: bool = False):
        self.calls: list[list[str]] = []
        self.misaligned = misaligned or set()
        self.refuse = refuse

    def translate(self, texts):
        self.calls.append(list(texts))
        if self.refuse:
            raise TranslationRefused("cyber")
        if len(texts) in self.misaligned:
            raise ValueError("translation line count mismatch")
        return [f"zh:{t}" for t in texts]


def _sentence(db, lesson_id: str, idx: int, text_zh: str = PLACEHOLDER) -> Sentence:
    s = Sentence(
        id=f"{lesson_id}:s{idx}",
        lesson_id=lesson_id,
        idx=idx,
        start_ms=idx * 1000,
        end_ms=(idx + 1) * 1000,
        text_en=f"Line {idx}.",
        text_zh=text_zh,
        difficulty="easy",
    )
    db.add(s)
    return s


@pytest.fixture
def library(db):
    for i in range(5):
        _sentence(db, "yt_aaa", i)
    for i in range(3):
        _sentence(db, "yt_bbb", i)
    db.commit()


def test_batches_never_span_two_lessons():
    """A batch is a scene: mixing two videos into one call gives the model
    context that actively misleads it."""
    a = [Sentence(id=f"a{i}", lesson_id="a", idx=i) for i in range(3)]
    b = [Sentence(id=f"b{i}", lesson_id="b", idx=i) for i in range(2)]
    batches = _grouped(a + b, size=10)
    assert [len(x) for x in batches] == [3, 2]
    assert {s.lesson_id for s in batches[0]} == {"a"}


def test_batches_respect_the_size_limit():
    rows = [Sentence(id=f"a{i}", lesson_id="a", idx=i) for i in range(7)]
    assert [len(b) for b in _grouped(rows, size=3)] == [3, 3, 1]


def test_translates_only_the_placeholders(db, library):
    already = db.get(Sentence, "yt_bbb:s0")
    already.text_zh = "已翻译"
    db.commit()

    translator = FakeTranslator()
    run(db, translator)

    assert db.get(Sentence, "yt_bbb:s0").text_zh == "已翻译"  # untouched
    assert db.get(Sentence, "yt_aaa:s0").text_zh == "zh:Line 0."
    assert all("已翻译" not in t for call in translator.calls for t in call)


def test_all_flag_retranslates_finished_sentences(db, library):
    db.get(Sentence, "yt_bbb:s0").text_zh = "旧的翻译"
    db.commit()

    run(db, FakeTranslator(), redo_all=True)
    assert db.get(Sentence, "yt_bbb:s0").text_zh == "zh:Line 0."


def test_a_misaligned_reply_halves_the_batch_instead_of_losing_it(db, library):
    """The model occasionally returns the wrong number of lines. Dropping the
    batch would leave a hole; splitting isolates whichever line caused it."""
    translator = FakeTranslator(misaligned={5})  # the 5-sentence lesson fails whole
    run(db, translator, batch_size=20)

    assert [len(c) for c in translator.calls] == [5, 2, 3, 3]  # split, then halves
    assert db.get(Sentence, "yt_aaa:s0").text_zh == "zh:Line 0."


def test_a_single_unusable_line_is_skipped_not_fatal(db):
    _sentence(db, "yt_ccc", 0)
    db.commit()

    translator = FakeTranslator(misaligned={1})
    assert translate_batch([db.get(Sentence, "yt_ccc:s0")], translator) == 0
    assert db.get(Sentence, "yt_ccc:s0").text_zh == PLACEHOLDER


def test_a_refused_batch_does_not_abort_the_run(db, library):
    """A refusal is about that batch's content, not the job — the remaining
    lessons must still get translated."""

    class RefuseFirst(FakeTranslator):
        def translate(self, texts):
            if not self.calls:
                self.calls.append(list(texts))
                raise TranslationRefused("cyber")
            return super().translate(texts)

    translator = RefuseFirst()
    run(db, translator, batch_size=20)

    assert db.get(Sentence, "yt_aaa:s0").text_zh == PLACEHOLDER  # refused batch
    assert db.get(Sentence, "yt_bbb:s0").text_zh == "zh:Line 0."  # kept going


def test_limit_bounds_the_run(db, library):
    translator = FakeTranslator()
    run(db, translator, batch_size=20, limit=4)
    assert sum(len(c) for c in translator.calls) == 4
