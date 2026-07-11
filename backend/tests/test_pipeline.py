import pytest
from sqlalchemy import func, select

from app.content.validator import validate_package
from app.db.models import Lesson, Sentence, WordIndex
from app.pipeline.captions import CaptionCue, NoCaptionsError, Segment, segment_into_sentences
from app.pipeline.nlp import PlaceholderTranslator, lemmatize, tokenize
from app.pipeline.pipeline import LessonMeta, build_lesson_package, ingest_youtube


class FakeFetcher:
    def __init__(self, cues):
        self._cues = cues

    def fetch(self, youtube_id):
        return list(self._cues)


class TagTranslator:
    """Deterministic non-placeholder translator for tests."""

    def translate(self, texts):
        return [f"[zh] {t}" for t in texts]


# ---- segmentation ----------------------------------------------------------

def test_segment_splits_on_punctuation():
    cues = [
        CaptionCue("How's it", 0, 800),
        CaptionCue("going?", 800, 1600),
        CaptionCue("I'm good.", 1600, 2600),
    ]
    segs = segment_into_sentences(cues)
    assert [s.text for s in segs] == ["How's it going?", "I'm good."]
    assert segs[0].start_ms == 0 and segs[0].end_ms == 1600
    assert segs[1].start_ms == 1600 and segs[1].end_ms == 2600


def test_segment_splits_on_big_gap_without_punctuation():
    cues = [
        CaptionCue("hello there", 0, 1000),
        CaptionCue("much later", 5000, 6000),  # >1.2s gap
    ]
    segs = segment_into_sentences(cues)
    assert [s.text for s in segs] == ["hello there", "much later"]


def test_segment_enforces_monotonic_nonoverlapping():
    cues = [CaptionCue("a b c.", 500, 400)]  # end <= start on purpose
    (seg,) = segment_into_sentences(cues)
    assert seg.start_ms < seg.end_ms


def test_segment_empty_input():
    assert segment_into_sentences([]) == []


# ---- tokenize / lemmatize --------------------------------------------------

def test_tokenize_char_spans_roundtrip():
    text = "How's it going?"
    toks = tokenize(text)
    assert [t["surface"] for t in toks] == ["How's", "it", "going"]
    for t in toks:
        s, e = t["char_span"]
        assert text[s:e] == t["surface"]


def test_lemmatize_rules():
    assert lemmatize("going") == "go"
    assert lemmatize("running") == "run"
    assert lemmatize("cats") == "cat"
    assert lemmatize("studies") == "study"
    assert lemmatize("was") == "be"
    assert lemmatize("nice") == "nice"


# ---- build package ---------------------------------------------------------

def _sample_segments():
    return [
        Segment("How's it going?", 0, 1600),
        Segment("I am going home.", 1600, 3200),
    ]


def test_build_package_is_valid():
    meta = LessonMeta(youtube_id="abc12345678", title="Chat", theme="small_talk")
    pkg = build_lesson_package(meta, _sample_segments(), TagTranslator())
    assert validate_package(pkg) == []
    assert pkg["video"]["id"] == "yt_abc12345678"
    assert pkg["video"]["duration_ms"] == 3200
    assert pkg["sentences"][1]["text_zh"] == "[zh] I am going home."


def test_build_package_dedups_index_per_sentence():
    meta = LessonMeta(youtube_id="abc12345678", title="x", theme="t")
    # "go" appears twice in one sentence -> one index row for that sentence
    segs = [Segment("go go go now.", 0, 1000)]
    pkg = build_lesson_package(meta, segs, PlaceholderTranslator())
    go_rows = [r for r in pkg["index"] if r["lemma"] == "go"]
    assert len(go_rows) == 1


def test_build_package_empty_raises():
    meta = LessonMeta(youtube_id="abc12345678", title="x", theme="t")
    with pytest.raises(NoCaptionsError):
        build_lesson_package(meta, [], PlaceholderTranslator())


# ---- full ingest -----------------------------------------------------------

def test_ingest_loads_and_indexes(db):
    cues = [
        CaptionCue("How's it going?", 0, 1600),
        CaptionCue("I am going home.", 1600, 3200),
    ]
    meta = LessonMeta(youtube_id="abc12345678", title="Chat", theme="small_talk")
    lesson = ingest_youtube(db, meta, FakeFetcher(cues), TagTranslator())

    assert lesson.id == "yt_abc12345678"
    assert db.scalar(select(func.count()).select_from(Sentence)) == 2
    # "go" (from "going" x2) is reverse-lookup-able across the lesson
    rows = db.scalars(select(WordIndex).where(WordIndex.lemma == "go")).all()
    assert len(rows) == 2


def test_ingest_is_idempotent(db):
    cues = [CaptionCue("Hello there.", 0, 1000)]
    meta = LessonMeta(youtube_id="abc12345678", title="Hi", theme="greeting")
    ingest_youtube(db, meta, FakeFetcher(cues), PlaceholderTranslator())
    ingest_youtube(db, meta, FakeFetcher(cues), PlaceholderTranslator())
    assert db.scalar(select(func.count()).select_from(Lesson)) == 1
