import pytest

from app.content.backfill import get_backfill_trigger
from app.db.seed import seed_initial
from app.main import app
from app.pipeline.captions import CaptionCue
from app.pipeline.nlp import PlaceholderTranslator
from app.pipeline.pipeline import LessonMeta, ingest_youtube


@pytest.fixture
def seeded(client, db):
    """Seed the sample lesson into the DB shared with the TestClient."""
    seed_initial(db)
    return client


@pytest.fixture
def backfill_spy():
    """Record lemmas the word-lookup endpoint schedules for backfill, without
    running the real (network-touching) job."""
    calls: list[str] = []
    app.dependency_overrides[get_backfill_trigger] = lambda: (
        lambda background_tasks, lemma: calls.append(lemma)
    )
    try:
        yield calls
    finally:
        app.dependency_overrides.pop(get_backfill_trigger, None)


class _FakeFetcher:
    def __init__(self, cues):
        self._cues = cues

    def fetch(self, youtube_id):
        return list(self._cues)


@pytest.fixture
def feed_lessons(client, db):
    """Two multi-clip lessons so feed ranking/paging is exercised."""
    for yid, theme in [("aaaaaaaaaaa", "small_talk"), ("bbbbbbbbbbb", "travel")]:
        cues = [CaptionCue(f"Sentence {i}.", i * 40_000, (i + 1) * 40_000) for i in range(5)]
        meta = LessonMeta(youtube_id=yid, title=f"L {yid}", theme=theme)
        ingest_youtube(db, meta, _FakeFetcher(cues), PlaceholderTranslator())
    return client


def test_list_lessons(seeded):
    resp = seeded.get("/api/lessons")
    assert resp.status_code == 200
    lessons = resp.json()
    assert len(lessons) == 1
    assert lessons[0]["id"] == "vid_smalltalk_001"
    assert lessons[0]["youtube_id"] == "dQw4w9WgXcQ"


def test_list_lessons_filters(seeded):
    assert len(seeded.get("/api/lessons", params={"theme": "small_talk"}).json()) == 1
    assert len(seeded.get("/api/lessons", params={"theme": "travel"}).json()) == 0
    assert len(seeded.get("/api/lessons", params={"difficulty": "easy"}).json()) == 1
    assert len(seeded.get("/api/lessons", params={"difficulty": "hard"}).json()) == 0


def test_get_lesson_detail_has_sentences_and_tokens(seeded):
    resp = seeded.get("/api/lessons/vid_smalltalk_001")
    assert resp.status_code == 200
    lesson = resp.json()
    assert len(lesson["sentences"]) == 2
    first = lesson["sentences"][0]
    assert first["text_en"] == "How's it going?"
    tok = first["tokens"][0]
    assert tok["char_span"] == [0, 5]  # tuple serialized as JSON array
    assert tok["surface"] == "How's"


def test_get_missing_lesson_404(seeded):
    assert seeded.get("/api/lessons/nope").status_code == 404


def test_word_occurrences(seeded):
    resp = seeded.get("/api/words/go/occurrences")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    occ = body["occurrences"][0]
    assert occ["lesson_id"] == "vid_smalltalk_001"
    assert occ["sentence_id"] == "vid_smalltalk_001:s1"
    assert occ["start_ms"] == 0


def test_word_occurrences_case_insensitive(seeded):
    assert seeded.get("/api/words/GO/occurrences").json()["count"] == 1


def test_word_occurrences_resolves_surface_form(seeded):
    # "going" lemmatizes to "go", which the sample lesson indexes
    body = seeded.get("/api/words/going/occurrences").json()
    assert body["lemma"] == "go"
    assert body["count"] == 1


def test_word_occurrences_unknown_lemma(seeded):
    body = seeded.get("/api/words/zzzznope/occurrences").json()
    assert body["count"] == 0
    assert body["occurrences"] == []


# ---- backfill wiring -------------------------------------------------------

def test_lookup_schedules_backfill_when_under_covered(seeded, backfill_spy):
    # "go" occurs once in the sample lesson — below MIN_COVERAGE (3)
    seeded.get("/api/words/go/occurrences")
    assert backfill_spy == ["go"]


def test_lookup_no_backfill_when_well_covered(feed_lessons, backfill_spy):
    # "sentence" occurs 10x across the two feed lessons — well covered
    body = feed_lessons.get("/api/words/sentence/occurrences").json()
    assert body["count"] >= 3
    assert backfill_spy == []


def test_lookup_schedules_backfill_for_unknown_word(seeded, backfill_spy):
    seeded.get("/api/words/zzzznope/occurrences")
    assert backfill_spy == ["zzzznope"]


# ---- feed ------------------------------------------------------------------

def test_feed_returns_clips_with_playback_fields(seeded):
    resp = seeded.get("/api/feed")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["clips"]) >= 1
    clip = body["clips"][0]
    assert clip["youtube_id"] == "dQw4w9WgXcQ"
    assert clip["start_ms"] < clip["end_ms"]
    assert clip["duration_ms"] == clip["end_ms"] - clip["start_ms"]
    assert clip["text_en"]


def test_feed_interleaves_lessons(feed_lessons):
    # Each 200s lesson yields 3 clips (start_idx 0, 2, 4); ordering by start_idx
    # interleaves lessons, so the first two feed items are different lessons.
    body = feed_lessons.get("/api/feed").json()
    assert len(body["clips"]) == 6
    assert body["clips"][0]["lesson_id"] != body["clips"][1]["lesson_id"]


def test_feed_pagination(feed_lessons):
    first = feed_lessons.get("/api/feed", params={"limit": 4}).json()
    assert len(first["clips"]) == 4
    assert first["next_offset"] == 4

    second = feed_lessons.get("/api/feed", params={"limit": 4, "offset": 4}).json()
    assert len(second["clips"]) == 2
    assert second["next_offset"] is None  # last page

    ids = {c["clip_id"] for c in first["clips"]} | {c["clip_id"] for c in second["clips"]}
    assert len(ids) == 6  # no overlap across pages


def test_feed_filters_by_theme(feed_lessons):
    body = feed_lessons.get("/api/feed", params={"theme": "travel"}).json()
    assert len(body["clips"]) == 3
    assert all(c["theme"] == "travel" for c in body["clips"])


def test_feed_empty_when_no_content(client):
    body = client.get("/api/feed").json()
    assert body["clips"] == []
    assert body["next_offset"] is None
