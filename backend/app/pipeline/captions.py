"""Caption fetching + sentence segmentation.

A CaptionFetcher yields raw timed cues (often sub-sentence fragments); the
segmenter merges them into sentence-ish units with clean start/end_ms that the
Reader can seek to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class NoCaptionsError(Exception):
    """Raised when a video has no usable caption track."""


@dataclass
class CaptionCue:
    text: str
    start_ms: int
    end_ms: int


@dataclass
class Segment:
    text: str
    start_ms: int
    end_ms: int


class CaptionFetcher(Protocol):
    def fetch(self, youtube_id: str) -> list[CaptionCue]:
        ...


class YouTubeTranscriptFetcher:
    """Fetches captions via youtube-transcript-api (network required).

    Kept thin and imported lazily so the rest of the pipeline has no hard
    dependency on it (and tests never touch the network).
    """

    def __init__(self, languages: tuple[str, ...] = ("en",)):
        self.languages = list(languages)

    def fetch(self, youtube_id: str) -> list[CaptionCue]:
        # youtube-transcript-api >= 1.0 API: instance .fetch() -> FetchedTranscript.
        from youtube_transcript_api import (  # noqa: PLC0415
            NoTranscriptFound,
            TranscriptsDisabled,
            YouTubeTranscriptApi,
        )

        try:
            fetched = YouTubeTranscriptApi().fetch(youtube_id, languages=self.languages)
        except (TranscriptsDisabled, NoTranscriptFound) as exc:
            raise NoCaptionsError(f"no captions for {youtube_id}") from exc

        cues: list[CaptionCue] = []
        for snip in fetched:
            start_ms = int(snip.start * 1000)
            end_ms = start_ms + int(snip.duration * 1000)
            cues.append(
                CaptionCue(text=snip.text.replace("\n", " "), start_ms=start_ms, end_ms=end_ms)
            )
        return cues


_SENTENCE_END = ".?!"


def segment_into_sentences(
    cues: list[CaptionCue],
    *,
    max_words: int = 14,
    gap_ms: int = 1200,
) -> list[Segment]:
    """Merge cues into sentences.

    A sentence closes when the accumulated text ends with .?!, reaches max_words,
    or a large silent gap precedes the next cue. Output is guaranteed monotonic
    and non-overlapping with start_ms < end_ms (so it passes package validation).
    """
    clean = [c for c in cues if c.text.strip()]
    segments: list[Segment] = []

    parts: list[str] = []
    start: int | None = None
    end: int | None = None
    words = 0

    for i, cue in enumerate(clean):
        text = " ".join(cue.text.split())
        if start is None:
            start = cue.start_ms
        parts.append(text)
        end = cue.end_ms
        words += len(text.split())

        ends_sentence = text[-1] in _SENTENCE_END if text else False
        is_last = i == len(clean) - 1
        big_gap = not is_last and (clean[i + 1].start_ms - cue.end_ms) > gap_ms

        if ends_sentence or words >= max_words or big_gap or is_last:
            segments.append(Segment(text=" ".join(parts), start_ms=start, end_ms=end))
            parts, start, end, words = [], None, None, 0

    # Enforce monotonic, non-overlapping, positive-length spans.
    prev_end = 0
    for seg in segments:
        if seg.start_ms < prev_end:
            seg.start_ms = prev_end
        if seg.end_ms <= seg.start_ms:
            seg.end_ms = seg.start_ms + 1
        prev_end = seg.end_ms

    return segments
