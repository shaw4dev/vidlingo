from sqlalchemy import func, select

from app.db.models import Lesson, WordSearch
from app.pipeline.captions import CaptionCue, CaptionsBlockedError, NoCaptionsError
from app.pipeline.discovery import PlaylistSource, VideoCandidate
from app.pipeline.nlp import PlaceholderTranslator
from app.pipeline.pipeline import LessonMeta, ingest_from_cues
from app.pipeline.sourcing import backfill_word, seed_corpus

# Real YouTube IDs are exactly 11 chars ([A-Za-z0-9_-]{11}); the validator
# enforces it, so test fixtures use 11-char ids too.
HAS_CAPS = "hascaps0001"
NO_CAPS = "nocaps00001"
DUP = "dupdupdup01"
NEW = "newnewnew01"
MATCH = "matchmatch1"
NOMATCH = "nomatchno01"
SEED = "seedseed001"
VID = "vvvvvvvvvvv"


class FakeAPI:
    def __init__(self, *, search=None, playlists=None):
        self._search = search or {}
        self._playlists = playlists or {}

    def search_videos(self, query, max_results=25):
        return self._search.get(query, [])[:max_results]

    def playlist_video_ids(self, pid, max_results=200):
        return self._playlists.get(pid, [])[:max_results]


class FakeFetcher:
    """youtube_id -> cues; a missing id raises NoCaptionsError (like a real miss)."""

    def __init__(self, transcripts):
        self._t = transcripts

    def fetch(self, youtube_id):
        cues = self._t.get(youtube_id)
        if cues is None:
            raise NoCaptionsError(youtube_id)
        return list(cues)


def _cue(text):
    return [CaptionCue(text, 0, 2000)]


# ---- seed_corpus -----------------------------------------------------------

def test_seed_ingests_captioned_skips_others(db):
    api = FakeAPI(playlists={"PL1": [
        VideoCandidate(HAS_CAPS, "Good"),
        VideoCandidate(NO_CAPS, "Silent"),
    ]})
    fetcher = FakeFetcher({HAS_CAPS: _cue("Hello there friend.")})  # NO_CAPS absent -> miss
    report = seed_corpus(db, [PlaylistSource("PL1")], api, fetcher, PlaceholderTranslator())

    assert report.ingested == [HAS_CAPS]
    assert report.skipped_no_captions == [NO_CAPS]
    assert db.get(Lesson, f"yt_{HAS_CAPS}") is not None


def test_seed_skips_already_ingested_and_dedups(db):
    ingest_from_cues(
        db, LessonMeta(youtube_id=DUP, title="x", theme="t"), _cue("Some words here."),
        PlaceholderTranslator(),
    )
    api = FakeAPI(playlists={
        "PL1": [VideoCandidate(DUP, "Dup"), VideoCandidate(NEW, "New")],
        "PL2": [VideoCandidate(NEW, "New again")],  # same id via another source
    })
    fetcher = FakeFetcher({NEW: _cue("Fresh content today.")})
    report = seed_corpus(
        db, [PlaylistSource("PL1"), PlaylistSource("PL2")], api, fetcher, PlaceholderTranslator()
    )

    assert report.ingested == [NEW]
    assert report.skipped_existing == [DUP]
    assert db.scalar(select(func.count()).select_from(Lesson)) == 2


# ---- backfill_word ---------------------------------------------------------

def test_backfill_only_ingests_videos_containing_the_word(db):
    # search returns two hits; only one's captions actually contain "run"
    api = FakeAPI(search={"run": [
        VideoCandidate(MATCH, "About running"),
        VideoCandidate(NOMATCH, "Clickbait title with run"),
    ]})
    fetcher = FakeFetcher({
        MATCH: _cue("I love running every morning."),  # running -> lemma run
        NOMATCH: _cue("This is about cooking pasta."),  # no 'run'
    })
    report = backfill_word(db, "run", api, fetcher, PlaceholderTranslator(), min_coverage=1)

    assert report.ingested == [MATCH]
    assert db.get(Lesson, f"yt_{MATCH}") is not None
    assert db.get(Lesson, f"yt_{NOMATCH}") is None
    assert db.get(WordSearch, "run") is not None  # search recorded


def test_backfill_short_circuits_when_already_covered(db):
    ingest_from_cues(
        db, LessonMeta(youtube_id=SEED, title="x", theme="t"),
        _cue("run run run fast."), PlaceholderTranslator(),
    )
    called = {"n": 0}

    class CountingAPI(FakeAPI):
        def search_videos(self, query, max_results=25):
            called["n"] += 1
            return []

    report = backfill_word(
        db, "run", CountingAPI(), FakeFetcher({}), PlaceholderTranslator(), min_coverage=1
    )
    assert report.already_covered is True
    assert called["n"] == 0  # no quota spent


def test_backfill_uses_cache_to_avoid_repeat_search(db):
    db.add(WordSearch(lemma="rare", ingested_count=0))
    db.commit()

    class BoomAPI(FakeAPI):
        def search_videos(self, query, max_results=25):
            raise AssertionError("should not search — cached")

    report = backfill_word(
        db, "rare", BoomAPI(), FakeFetcher({}), PlaceholderTranslator(), min_coverage=1
    )
    assert report.cached_skip is True


def test_backfill_force_ignores_cache(db):
    db.add(WordSearch(lemma="run", ingested_count=0))
    db.commit()
    api = FakeAPI(search={"run": [VideoCandidate(VID, "Running tips")]})
    fetcher = FakeFetcher({VID: _cue("Keep running strong.")})
    report = backfill_word(
        db, "run", api, fetcher, PlaceholderTranslator(), min_coverage=1, force=True
    )
    assert report.ingested == [VID]


# ---- blocked-by-YouTube circuit breaker ------------------------------------

class BlockingFetcher:
    """Serves `ok_ids` normally, then blocks — like YouTube cutting us off
    partway through a batch."""

    def __init__(self, transcripts, block_after):
        self._t = transcripts
        self._left = block_after
        self.calls = 0

    def fetch(self, youtube_id):
        self.calls += 1
        if self._left <= 0:
            raise CaptionsBlockedError("YouTube is blocking requests from your IP")
        self._left -= 1
        cues = self._t.get(youtube_id)
        if cues is None:
            raise NoCaptionsError(youtube_id)
        return list(cues)


def test_seed_aborts_on_block_and_keeps_earlier_work(db):
    api = FakeAPI(playlists={"PL1": [
        VideoCandidate(HAS_CAPS, "Good"),
        VideoCandidate(NEW, "Blocked"),
        VideoCandidate(DUP, "Never reached"),
    ]})
    fetcher = BlockingFetcher({HAS_CAPS: _cue("Hello there friend."),
                               NEW: _cue("Second one."),
                               DUP: _cue("Third one.")}, block_after=1)

    report = seed_corpus(db, [PlaylistSource("PL1")], api, fetcher, PlaceholderTranslator())

    assert report.ingested == [HAS_CAPS]        # work before the block is kept
    assert report.blocked                        # and reported as an abort
    assert report.failed == []                   # a block is not a per-video failure
    assert fetcher.calls == 2                    # stopped instead of grinding on
    assert "ABORTED" in report.summary
    assert db.get(Lesson, f"yt_{HAS_CAPS}") is not None


def test_backfill_block_does_not_poison_the_search_cache(db):
    """A block means the lemma was never really searched. Caching it here would
    skip the word forever."""
    api = FakeAPI(search={"jump": [VideoCandidate(VID, "Jumping")]})
    fetcher = BlockingFetcher({VID: _cue("They jump high.")}, block_after=0)

    report = backfill_word(db, "jump", api, fetcher, PlaceholderTranslator())

    assert report.blocked
    assert report.ingested == []
    assert db.get(WordSearch, "jump") is None    # retryable later
    assert "retry later" in report.summary
