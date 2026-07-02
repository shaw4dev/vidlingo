import pytest

from app.db.seed import seed_initial


@pytest.fixture
def seeded(client, db):
    """Seed the sample lesson into the DB shared with the TestClient."""
    seed_initial(db)
    return client


def test_list_lessons(seeded):
    resp = seeded.get("/lessons")
    assert resp.status_code == 200
    lessons = resp.json()
    assert len(lessons) == 1
    assert lessons[0]["id"] == "vid_smalltalk_001"
    assert lessons[0]["youtube_id"] == "dQw4w9WgXcQ"


def test_list_lessons_filters(seeded):
    assert len(seeded.get("/lessons", params={"theme": "small_talk"}).json()) == 1
    assert len(seeded.get("/lessons", params={"theme": "travel"}).json()) == 0
    assert len(seeded.get("/lessons", params={"difficulty": "easy"}).json()) == 1
    assert len(seeded.get("/lessons", params={"difficulty": "hard"}).json()) == 0


def test_get_lesson_detail_has_sentences_and_tokens(seeded):
    resp = seeded.get("/lessons/vid_smalltalk_001")
    assert resp.status_code == 200
    lesson = resp.json()
    assert len(lesson["sentences"]) == 2
    first = lesson["sentences"][0]
    assert first["text_en"] == "How's it going?"
    tok = first["tokens"][0]
    assert tok["char_span"] == [0, 5]  # tuple serialized as JSON array
    assert tok["surface"] == "How's"


def test_get_missing_lesson_404(seeded):
    assert seeded.get("/lessons/nope").status_code == 404


def test_word_occurrences(seeded):
    resp = seeded.get("/words/go/occurrences")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    occ = body["occurrences"][0]
    assert occ["lesson_id"] == "vid_smalltalk_001"
    assert occ["sentence_id"] == "vid_smalltalk_001:s1"
    assert occ["start_ms"] == 0


def test_word_occurrences_case_insensitive(seeded):
    assert seeded.get("/words/GO/occurrences").json()["count"] == 1


def test_word_occurrences_unknown_lemma(seeded):
    body = seeded.get("/words/zzzznope/occurrences").json()
    assert body["count"] == 0
    assert body["occurrences"] == []
