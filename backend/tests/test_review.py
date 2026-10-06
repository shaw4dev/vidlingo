"""Review API tests: the queue, the cap, and grading.

HTTP-only, in the style of test_vocab.py. The scheduling arithmetic is proved
exhaustively in test_srs.py against the pure functions; what can actually break
here is the plumbing — ownership, idempotency, the cap, and whether a card
carries enough to be rendered.
"""

from datetime import UTC, datetime

import pytest

from app.db.models import ReviewLog, VocabItem
from app.db.seed import seed_initial
from app.srs import sm2

# The sample package's own sentences are three words long, which is under
# MIN_CLOZE_WORDS -- they exercise the short-sentence path, not the cloze one.
# Anything testing a real cloze has to bring its own sentence.
SENTENCE_ID = "vid_smalltalk_001:s1"  # "How's it going?" — 3 words, token lemma "go"
LESSON_ID = "vid_smalltalk_001"


@pytest.fixture
def seeded(client, db):
    seed_initial(db)
    return client


def _add_sentence(db, sid, text_en, text_zh, *, idx=50, start_ms=0, end_ms=3000):
    """Insert a sentence with its tokens and reverse-index rows, as ingest does.

    Offsets are scanned rather than written by hand: a char span one out would
    silently blank the wrong word, which is the exact bug the span assertions
    here exist to catch -- so the fixture must not be able to introduce it.
    """
    from app.db.models import Sentence, Token, WordIndex

    db.add(
        Sentence(
            id=sid,
            lesson_id=LESSON_ID,
            idx=idx,
            start_ms=start_ms,
            end_ms=end_ms,
            text_en=text_en,
            text_zh=text_zh,
            difficulty="easy",
        )
    )
    at = 0
    for word in text_en.split(" "):
        start = text_en.index(word, at)
        end = start + len(word)
        at = end
        lemma = word.strip(".,?!").lower()
        if not lemma:
            continue
        db.add(Token(sentence_id=sid, char_start=start, char_end=end, surface=word, lemma=lemma))
        db.add(WordIndex(lemma=lemma, sentence_id=sid, lesson_id=LESSON_ID, start_ms=start_ms))
    db.commit()


def _auth(client, username="alice", password="secret123"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@x.com", "password": password},
    )
    token = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _save(client, headers, lemma, sentence_id=SENTENCE_ID):
    body = {"lemma": lemma}
    if sentence_id is not None:
        body["source_sentence_id"] = sentence_id
    resp = client.post("/api/vocab", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _grade(client, headers, item_id, grade, event_id, **extra):
    return client.post(
        "/api/review/grade",
        json={
            "client_event_id": event_id,
            "vocab_item_id": item_id,
            "grade": grade,
            **extra,
        },
        headers=headers,
    )


# --- the queue -------------------------------------------------------------


def test_a_fresh_user_has_nothing_to_review(seeded):
    h = _auth(seeded)
    body = seeded.get("/api/review/queue", headers=h).json()
    assert body["cards"] == []
    assert body["due_total"] == 0
    assert body["scheduled_today"] == 0
    assert body["next_due_at"] is None


LONG_EN = "I am just trying to give you a break here."
LONG_ZH = "我只是想让你歇一歇。"


def test_a_saved_word_is_reviewable_immediately(seeded, db):
    _add_sentence(db, "s:long", LONG_EN, LONG_ZH)
    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id="s:long")

    body = seeded.get("/api/review/queue", headers=h).json()
    assert len(body["cards"]) == 1

    card = body["cards"][0]
    assert card["lemma"] == "break"
    assert card["mastery"] == "new"
    assert card["card_kind"] == "cloze"
    # The Chinese line is what makes the blank answerable at all.
    assert card["source"]["text_zh"] == LONG_ZH
    assert card["source"]["borrowed"] is False
    assert card["source"]["end_ms"] > card["source"]["start_ms"]


def test_the_blanked_span_really_covers_the_word(seeded, db):
    """The one assertion that catches an off-by-one.

    A span that is merely present would still ship a card with the wrong word
    hidden, which looks like a content bug rather than a code bug.
    """
    _add_sentence(db, "s:long", LONG_EN, LONG_ZH)
    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id="s:long")

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    text = card["source"]["text_en"]
    spans = card["source"]["blank_spans"]
    assert spans, "no span to blank"
    for start, end in spans:
        assert text[start:end].lower() == "break"


def test_every_occurrence_is_blanked(seeded, db):
    """Leaving a second copy visible hands over the answer."""
    _add_sentence(
        db,
        "s:twice",
        "You can take a break now or take a break later.",
        "你可以现在休息一下或者待会儿休息。",
    )
    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id="s:twice")

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    text = card["source"]["text_en"]
    spans = card["source"]["blank_spans"]
    assert len(spans) == 2, f"only blanked {len(spans)} of two occurrences"
    assert all(text[a:b].lower() == "break" for a, b in spans)


def test_a_word_with_no_source_borrows_a_sentence(seeded, db):
    """Saved from the word-detail page, so it has no sentence of its own —
    the reverse index supplies one rather than degrading the card."""
    _add_sentence(db, "s:long", LONG_EN, LONG_ZH)
    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id=None)

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    assert card["source"] is not None
    assert card["source"]["sentence_id"] == "s:long"
    assert card["source"]["borrowed"] is True
    assert card["card_kind"] == "cloze"


# --- short sentences -------------------------------------------------------


def test_a_short_sentence_is_swapped_for_a_longer_one(seeded, db):
    """A three-word line cannot host a cloze; the reverse index has a better one."""
    _add_sentence(db, "s:short", "Take a break.", "休息一下。", idx=60, start_ms=9000)
    _add_sentence(db, "s:long", LONG_EN, LONG_ZH, idx=61)

    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id="s:short")

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    assert card["source"]["sentence_id"] == "s:long"
    assert card["source"]["borrowed"] is True
    assert card["card_kind"] == "cloze"


def test_a_short_sentence_with_no_alternative_falls_back_to_chinese(seeded, db):
    """The share the reverse index cannot rescue.

    A blank standing in for the whole sentence is not a question. The Chinese
    line already is one, so ask for the English instead.
    """
    _add_sentence(db, "s:only", "Take a nap.", "睡一会儿。", idx=62)
    h = _auth(seeded)
    _save(seeded, h, "nap", sentence_id="s:only")

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    assert card["card_kind"] == "zh_prompt"
    assert card["source"]["blank_spans"] == []
    assert card["source"]["text_zh"] == "睡一会儿。"


def test_a_usable_sentence_is_never_swapped(seeded, db):
    """The hook is that this is the scene *you* met the word in.

    Substituting a perfectly good sentence trades the product's one
    differentiator for nothing.
    """
    _add_sentence(db, "s:mine", LONG_EN, LONG_ZH)
    _add_sentence(
        db,
        "s:other",
        "She said she really needed a break from all of this.",
        "她说她真的需要休息。",
        idx=63,
    )

    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id="s:mine")

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    assert card["source"]["sentence_id"] == "s:mine"
    assert card["source"]["borrowed"] is False


def test_the_substitute_is_stable_across_requests(seeded, db):
    """A card that shows a different example every time reads as a bug."""
    _add_sentence(db, "s:short", "Take a break.", "休息一下。", idx=64, start_ms=1000)
    _add_sentence(
        db,
        "s:a",
        "I really need to take a break right now.",
        "我真的需要休息。",
        idx=65,
        start_ms=2000,
    )
    _add_sentence(
        db,
        "s:b",
        "You should also take a break right now.",
        "你也应该休息。",
        idx=66,
        start_ms=3000,
    )

    h = _auth(seeded)
    _save(seeded, h, "break", sentence_id="s:short")

    first = seeded.get("/api/review/queue", headers=h).json()["cards"][0]["source"]["sentence_id"]
    second = seeded.get("/api/review/queue", headers=h).json()["cards"][0]["source"]["sentence_id"]
    assert first == second


def test_a_word_nobody_ever_said_still_makes_a_card(seeded):
    h = _auth(seeded)
    item = _save(seeded, h, "zzzznotaword", sentence_id=None)

    card = seeded.get("/api/review/queue", headers=h).json()["cards"][0]
    assert card["source"] is None
    assert card["card_kind"] == "bare"

    # And it is still gradeable — a card with no context is not a dead end.
    assert _grade(seeded, h, item["id"], "remembered", "evt-bare-1").status_code == 200


def test_the_queue_is_per_user(seeded):
    ha = _auth(seeded, "alice")
    hb = _auth(seeded, "bob")
    _save(seeded, ha, "go")
    assert seeded.get("/api/review/queue", headers=hb).json()["cards"] == []


# --- grading ---------------------------------------------------------------


def test_grading_advances_the_schedule_and_clears_the_queue(seeded):
    h = _auth(seeded)
    item = _save(seeded, h, "go")

    body = _grade(seeded, h, item["id"], "remembered", "evt-first-pass", latency_ms=1400).json()
    assert body["duplicate"] is False
    assert body["interval_days"] == 1
    assert body["reps"] == 1
    assert body["ease"] == sm2.DEFAULT_EASE + 10
    assert body["mastery"] == "learning"

    assert seeded.get("/api/review/queue", headers=h).json()["cards"] == []
    assert seeded.get("/api/review/summary", headers=h).json()["done_today"] == 1


def test_a_lapse_comes_back_in_the_same_session(seeded):
    h = _auth(seeded)
    item = _save(seeded, h, "go")

    body = _grade(seeded, h, item["id"], "forgot", "evt-lapse").json()
    assert body["interval_days"] == 0
    assert body["mastery"] == "new"

    due = datetime.fromisoformat(body["due_at"])
    assert due > datetime.now(UTC), "a lapsed card must be scheduled ahead, not in the past"

    # Not in the queue right now (it is ten minutes out), but not tomorrow
    # either — the retry is what makes failing a card useful.
    assert seeded.get("/api/review/queue", headers=h).json()["cards"] == []


def test_mastery_is_now_driven_by_grading(seeded):
    h = _auth(seeded)
    item = _save(seeded, h, "go")

    _grade(seeded, h, item["id"], "remembered", "evt-pass-a")
    assert seeded.get("/api/vocab", headers=h).json()[0]["mastery"] == "learning"

    _grade(seeded, h, item["id"], "forgot", "evt-lapse-b")
    assert seeded.get("/api/vocab", headers=h).json()[0]["mastery"] == "new"


def test_the_log_records_both_sides_of_the_decision(seeded, db):
    h = _auth(seeded)
    item = _save(seeded, h, "go")
    _grade(seeded, h, item["id"], "vague", "evt-logged-1", latency_ms=900, tz_offset=600)

    row = db.query(ReviewLog).one()
    assert (row.grade, row.quality) == ("vague", 3)
    assert (row.interval_before, row.interval_after) == (0, 1)
    assert row.ease_before == sm2.DEFAULT_EASE
    assert row.ease_after == sm2.DEFAULT_EASE - 14
    assert row.lemma == "go"
    assert row.latency_ms == 900
    assert row.tz_offset_minutes == 600
    assert row.next_due_at is not None


# --- idempotency -----------------------------------------------------------


def test_resubmitting_the_same_event_changes_nothing(seeded, db):
    """A retried tap must not advance the schedule twice."""
    h = _auth(seeded)
    item = _save(seeded, h, "go")

    first = _grade(seeded, h, item["id"], "remembered", "evt-same").json()
    second = _grade(seeded, h, item["id"], "remembered", "evt-same").json()

    assert second["duplicate"] is True
    assert second["due_at"] == first["due_at"]
    assert second["interval_days"] == first["interval_days"]
    assert second["ease"] == first["ease"]
    assert second["reps"] == first["reps"]

    assert db.query(ReviewLog).count() == 1
    assert db.query(VocabItem).one().reps == 1


def test_a_different_event_id_does_advance_the_same_word(seeded):
    """The guard keys on the event, not on the word."""
    h = _auth(seeded)
    item = _save(seeded, h, "go")

    _grade(seeded, h, item["id"], "remembered", "evt-pass-one")
    second = _grade(seeded, h, item["id"], "remembered", "evt-pass-two").json()
    assert second["duplicate"] is False
    assert second["reps"] == 2
    assert second["interval_days"] == 3


# --- the daily cap ---------------------------------------------------------


def test_the_cap_limits_the_queue_and_defers_the_rest(seeded):
    h = _auth(seeded)
    for lemma in ("go", "do", "have", "want", "know"):
        _save(seeded, h, lemma, sentence_id=None)

    body = seeded.get("/api/review/queue?limit=3", headers=h).json()
    assert len(body["cards"]) == 3
    assert body["due_total"] == 5
    assert body["scheduled_today"] == 3

    for i, card in enumerate(body["cards"]):
        resp = _grade(seeded, h, card["vocab_item_id"], "remembered", f"evt-cap-{i}")
        assert resp.status_code == 200, resp.text

    after = seeded.get("/api/review/queue?limit=3", headers=h).json()
    assert after["cards"] == [], "the cap is spent for today"
    assert after["done_today"] == 3
    # Nothing was dropped: the overflow is still due, just not today.
    assert after["due_total"] == 2


def test_a_lapse_does_not_consume_a_second_slot(seeded):
    """COUNT(DISTINCT ...) — otherwise a bad session shrinks its own quota."""
    h = _auth(seeded)
    item = _save(seeded, h, "go")

    _grade(seeded, h, item["id"], "forgot", "evt-lapse-x")
    _grade(seeded, h, item["id"], "forgot", "evt-lapse-y")

    assert seeded.get("/api/review/summary", headers=h).json()["done_today"] == 1


# --- timezone --------------------------------------------------------------


@pytest.mark.parametrize("offset", [0, 600, -300])
def test_day_start_matches_the_pure_function(seeded, offset):
    h = _auth(seeded)
    body = seeded.get(f"/api/review/summary?tz_offset={offset}", headers=h).json()
    expected = sm2.day_start_utc(datetime.now(UTC), offset)
    assert datetime.fromisoformat(body["day_start"]) == expected


def test_the_two_ends_of_the_dateline_get_different_days(seeded):
    h = _auth(seeded)
    east = seeded.get("/api/review/summary?tz_offset=840", headers=h).json()["day_start"]
    west = seeded.get("/api/review/summary?tz_offset=-720", headers=h).json()["day_start"]
    assert east != west


# --- rejections ------------------------------------------------------------


def test_grading_someone_elses_word_is_a_404(seeded, db):
    ha = _auth(seeded, "alice")
    hb = _auth(seeded, "bob")
    item = _save(seeded, ha, "go")

    assert _grade(seeded, hb, item["id"], "remembered", "evt-theft").status_code == 404
    assert db.query(VocabItem).filter_by(id=item["id"]).one().reps == 0


def test_grading_an_unknown_word_is_a_404(seeded):
    h = _auth(seeded)
    assert _grade(seeded, h, "nope", "remembered", "evt-nope").status_code == 404


def test_review_requires_auth(seeded):
    assert seeded.get("/api/review/queue").status_code == 401
    assert seeded.get("/api/review/summary").status_code == 401
    assert (
        seeded.post(
            "/api/review/grade",
            json={"client_event_id": "evt-anon", "vocab_item_id": "x", "grade": "remembered"},
        ).status_code
        == 401
    )


def test_nonsense_parameters_are_rejected(seeded):
    h = _auth(seeded)
    item = _save(seeded, h, "go")
    assert seeded.get("/api/review/queue?tz_offset=9999", headers=h).status_code == 422
    assert seeded.get("/api/review/queue?limit=0", headers=h).status_code == 422
    assert _grade(seeded, h, item["id"], "brilliant", "evt-bad-grade").status_code == 422
    # A client_event_id too short to be a real random id is refused, so a
    # client cannot accidentally make every card share one key.
    assert _grade(seeded, h, item["id"], "remembered", "short").status_code == 422
