from sqlalchemy import func, select

from app.db.models import Clip
from app.pipeline.captions import CaptionCue
from app.pipeline.clips import MAX_MS, MIN_MS, SentenceSpan, plan_clips
from app.pipeline.nlp import PlaceholderTranslator
from app.pipeline.pipeline import LessonMeta, ingest_youtube


def _spans(durations_ms, difficulty="easy"):
    """Build back-to-back sentence spans of the given durations."""
    spans, t = [], 0
    for i, d in enumerate(durations_ms):
        spans.append(
            SentenceSpan(idx=i, start_ms=t, end_ms=t + d, text_en=f"s{i}.", difficulty=difficulty)
        )
        t += d
    return spans


class FakeFetcher:
    def __init__(self, cues):
        self._cues = cues

    def fetch(self, youtube_id):
        return list(self._cues)


# ---- plan_clips (pure windowing) -------------------------------------------

def test_plan_clips_chunks_are_non_overlapping_and_contiguous():
    spans = _spans([20_000] * 9)  # 180s total in 20s sentences
    clips = plan_clips(spans)
    # contiguous from the start, no gaps, no overlap between windows
    assert clips[0].start_idx == 0
    for a, b in zip(clips, clips[1:], strict=False):
        assert b.start_idx == a.end_idx + 1
    # v0 tradeoff: a trailing sub-MIN window is dropped, so coverage may stop
    # short of the last sentence (idx 8 here). Those sentences are still
    # reverse-lookupable for word-detail; they just don't surface in the feed.
    assert clips[-1].end_idx == 7


def test_plan_clips_respects_max_length():
    spans = _spans([20_000] * 9)
    for c in plan_clips(spans):
        assert c.duration_ms <= MAX_MS


def test_plan_clips_drops_short_tail_window():
    # 90s worth (fills one window) + a lone 10s tail that's below MIN
    spans = _spans([30_000, 30_000, 30_000, 10_000])
    clips = plan_clips(spans)
    assert all(c.duration_ms >= MIN_MS for c in clips)
    assert clips[-1].end_idx == 2  # the 10s tail was dropped


def test_plan_clips_short_lesson_still_yields_one():
    spans = _spans([5_000, 5_000])  # 10s total, below MIN
    clips = plan_clips(spans)
    assert len(clips) == 1
    assert clips[0].start_idx == 0 and clips[0].end_idx == 1


def test_plan_clips_over_length_sentence_is_own_clip():
    spans = _spans([MAX_MS + 10_000])
    clips = plan_clips(spans)
    assert len(clips) == 1 and clips[0].duration_ms > MAX_MS


def test_plan_clips_difficulty_is_hardest_in_window():
    spans = _spans([40_000, 40_000])
    spans[1].difficulty = "hard"
    assert plan_clips(spans)[0].difficulty == "hard"


def test_plan_clips_empty():
    assert plan_clips([]) == []


# ---- integration: ingest generates clips -----------------------------------

def test_ingest_generates_clips(db):
    # three ~40s cues -> 120s lesson -> at least one clip persisted
    cues = [
        CaptionCue("How's it going?", 0, 40_000),
        CaptionCue("I am going home.", 40_000, 80_000),
        CaptionCue("See you later.", 80_000, 120_000),
    ]
    meta = LessonMeta(youtube_id="abc12345678", title="Chat", theme="small_talk")
    lesson = ingest_youtube(db, meta, FakeFetcher(cues), PlaceholderTranslator())

    clips = db.scalars(select(Clip).where(Clip.lesson_id == lesson.id)).all()
    assert len(clips) >= 1
    assert all(MIN_MS <= c.duration_ms for c in clips) or len(clips) == 1


def test_reingest_regenerates_clips_without_duplicates(db):
    cues = [CaptionCue("Hello there.", 0, 60_000)]
    meta = LessonMeta(youtube_id="abc12345678", title="Hi", theme="greeting")
    ingest_youtube(db, meta, FakeFetcher(cues), PlaceholderTranslator())
    n1 = db.scalar(select(func.count()).select_from(Clip))
    ingest_youtube(db, meta, FakeFetcher(cues), PlaceholderTranslator())
    n2 = db.scalar(select(func.count()).select_from(Clip))
    assert n1 == n2 == 1
