"""Generate feed clips (30-90s windows) from a lesson's sentences.

A clip is a contiguous run of sentences short enough to work as a TikTok-style
feed item. `plan_clips` is the pure, swappable windowing strategy (v0:
non-overlapping greedy chunks — see NOTE); `generate_clips` persists the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Clip, Lesson

MIN_MS = 30_000
MAX_MS = 90_000

_DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2}


@dataclass
class SentenceSpan:
    """The slice of sentence data windowing needs (works for package dicts and
    ORM rows alike — adapt at the call site)."""

    idx: int
    start_ms: int
    end_ms: int
    text_en: str
    difficulty: str


@dataclass
class ClipWindow:
    start_idx: int
    end_idx: int
    start_ms: int
    end_ms: int
    duration_ms: int
    difficulty: str
    text_en: str


def _close(window: list[SentenceSpan]) -> ClipWindow:
    first, last = window[0], window[-1]
    return ClipWindow(
        start_idx=first.idx,
        end_idx=last.idx,
        start_ms=first.start_ms,
        end_ms=last.end_ms,
        duration_ms=last.end_ms - first.start_ms,
        difficulty=max((s.difficulty for s in window), key=lambda d: _DIFF_ORDER.get(d, 0)),
        text_en=" ".join(s.text_en for s in window),
    )


def plan_clips(
    sentences: list[SentenceSpan], min_ms: int = MIN_MS, max_ms: int = MAX_MS
) -> list[ClipWindow]:
    """Split sentences into non-overlapping ~min..max-length windows.

    NOTE (v0 strategy, deliberately swappable): greedy accumulation, each
    sentence in exactly one window. A window closes when adding the next
    sentence would exceed `max_ms`. Windows shorter than `min_ms` are dropped —
    unless that would drop everything, in which case the single longest window is
    kept so short lessons still yield one clip. A lone sentence longer than
    `max_ms` becomes its own (over-length) clip since a sentence can't be split.
    """
    if not sentences:
        return []

    windows: list[list[SentenceSpan]] = []
    current: list[SentenceSpan] = []
    for s in sentences:
        if current and (s.end_ms - current[0].start_ms) > max_ms:
            windows.append(current)
            current = [s]
        else:
            current.append(s)
    if current:
        windows.append(current)

    clips = [_close(w) for w in windows]
    long_enough = [c for c in clips if c.duration_ms >= min_ms]
    if long_enough:
        return long_enough
    return [max(clips, key=lambda c: c.duration_ms)]  # fallback: keep the best one


def generate_clips(session: Session, lesson: Lesson, spans: list[SentenceSpan]) -> list[Clip]:
    """Replace `lesson`'s clips with freshly planned ones. Caller flushes/commits.

    Idempotent: the ORM cascade on Lesson.clips clears the old set first, so
    re-ingesting a lesson regenerates its clips without duplicates.
    """
    lesson.clips.clear()
    session.flush()

    clips = [
        Clip(
            lesson_id=lesson.id,
            start_idx=w.start_idx,
            end_idx=w.end_idx,
            start_ms=w.start_ms,
            end_ms=w.end_ms,
            duration_ms=w.duration_ms,
            difficulty=w.difficulty,
            text_en=w.text_en,
        )
        for w in plan_clips(spans)
    ]
    session.add_all(clips)
    return clips
