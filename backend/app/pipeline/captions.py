"""Caption fetching + sentence segmentation.

A CaptionFetcher yields raw timed cues (often sub-sentence fragments); the
segmenter merges them into sentence-ish units with clean start/end_ms that the
Reader can seek to.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class NoCaptionsError(Exception):
    """This video yields no usable captions — skip it and move on.

    Covers a missing/disabled caption track, but also videos we simply can't
    read: geo-restricted, age-gated, private, or deleted. They're all the same
    decision for the caller (skip one video), unlike CaptionsBlockedError.
    """


class CaptionsBlockedError(Exception):
    """YouTube is refusing our caption requests (IP rate-limit / bot check).

    Distinct from NoCaptionsError because it says nothing about the video: it's
    a property of *us*, and the next request will fail the same way. Callers
    must abort the batch rather than mark videos as individually failed —
    hammering on only deepens the block.
    """


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

    This endpoint is not part of the Data API — it's youtube.com's internal
    timedtext service, with no key and no quota, so YouTube polices it by IP.

    Measured against a residential IP: roughly 30-45 fetches per cooldown
    window, whether spaced 0s or 4s apart. So the binding limit is requests per
    window, not rate — `min_interval_s` softens the burst but cannot buy volume.
    Seeding a large library means either many small runs spread over hours, or
    routing through proxies (youtube-transcript-api supports both).
    """

    def __init__(self, languages: tuple[str, ...] = ("en",), *, min_interval_s: float = 5.0):
        self.languages = list(languages)
        self.min_interval_s = min_interval_s
        self._last_fetch = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_fetch)
        if wait > 0:
            time.sleep(wait)
        self._last_fetch = time.monotonic()

    def fetch(self, youtube_id: str) -> list[CaptionCue]:
        # youtube-transcript-api >= 1.0 API: instance .fetch() -> FetchedTranscript.
        from youtube_transcript_api import (  # noqa: PLC0415
            AgeRestricted,
            InvalidVideoId,
            NoTranscriptFound,
            PoTokenRequired,
            RequestBlocked,
            TranscriptsDisabled,
            VideoUnavailable,
            VideoUnplayable,
            YouTubeTranscriptApi,
        )

        # Order matters: the blocked check must come first, because it's the one
        # error that says "stop", and we must not mistake it for a bad video.
        self._throttle()
        try:
            fetched = YouTubeTranscriptApi().fetch(youtube_id, languages=self.languages)
        except (RequestBlocked, PoTokenRequired) as exc:  # IpBlocked subclasses RequestBlocked
            raise CaptionsBlockedError(str(exc).strip().splitlines()[0]) from exc
        except (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnplayable,  # geo-restricted, removed by uploader, ...
            VideoUnavailable,
            AgeRestricted,
            InvalidVideoId,
        ) as exc:
            raise NoCaptionsError(f"{type(exc).__name__} for {youtube_id}") from exc

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
