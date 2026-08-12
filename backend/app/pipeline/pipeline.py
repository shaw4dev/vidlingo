"""Assemble segments into a LessonPackage and ingest it into the DB."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Lesson
from app.db.seed import load_package
from app.pipeline.captions import (
    CaptionCue,
    CaptionFetcher,
    NoCaptionsError,
    Segment,
    segment_into_sentences,
)
from app.pipeline.nlp import Translator, tokenize


@dataclass
class LessonMeta:
    youtube_id: str
    title: str
    theme: str
    source: str | None = None
    license_tag: str = "youtube_embed"


def _difficulty(text: str) -> str:
    """Heuristic v0 difficulty (upgraded by a model later, backlog B5)."""
    words = text.split()
    n = len(words)
    avg_len = sum(len(w) for w in words) / n if n else 0
    score = n * 0.4 + avg_len
    if score < 8:
        return "easy"
    if score < 13:
        return "medium"
    return "hard"


def build_lesson_package(meta: LessonMeta, segments: list[Segment], translator: Translator) -> dict:
    if not segments:
        raise NoCaptionsError(f"no segments for {meta.youtube_id}")

    lesson_id = f"yt_{meta.youtube_id}"
    zh_list = translator.translate([s.text for s in segments])

    sentences = []
    index_seen: set[tuple[str, str]] = set()
    index_rows = []
    for i, (seg, zh) in enumerate(zip(segments, zh_list, strict=True)):
        local_id = f"s{i}"
        tokens = tokenize(seg.text)
        sentences.append(
            {
                "id": local_id,
                "idx": i,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "text_en": seg.text,
                "text_zh": zh,
                "difficulty": _difficulty(seg.text),
                "tokens": tokens,
            }
        )
        for tok in tokens:
            key = (tok["lemma"], local_id)
            if key in index_seen:
                continue
            index_seen.add(key)
            index_rows.append(
                {"lemma": tok["lemma"], "sentence_id": local_id, "start_ms": seg.start_ms}
            )

    duration_ms = max(s["end_ms"] for s in sentences)
    video = {
        "id": lesson_id,
        "provider": "youtube",
        "youtube_id": meta.youtube_id,
        "title": meta.title,
        "theme": meta.theme,
        "license_tag": meta.license_tag,
        "duration_ms": duration_ms,
    }
    if meta.source is not None:  # optional field: omit rather than send null
        video["source"] = meta.source
    return {
        "schema_version": 1,
        "package_version": 1,
        "video": video,
        "sentences": sentences,
        "index": index_rows,
    }


def ingest_from_cues(
    session: Session,
    meta: LessonMeta,
    cues: list[CaptionCue],
    translator: Translator,
) -> Lesson:
    """Ingest already-fetched caption cues: segment -> translate -> ... -> load.

    Split out from `ingest_youtube` so callers that must inspect captions before
    ingesting (e.g. word backfill verifying a lemma is present) don't fetch twice.
    """
    segments = segment_into_sentences(cues)
    package = build_lesson_package(meta, segments, translator)
    lesson = load_package(session, package)  # validates before insert (T02/T03)
    session.commit()
    return lesson


def ingest_youtube(
    session: Session,
    meta: LessonMeta,
    fetcher: CaptionFetcher,
    translator: Translator,
) -> Lesson:
    """Full pipeline: fetch -> segment -> translate -> tokenize -> validate -> load.

    Raises NoCaptionsError if the video has no usable captions, ValueError if the
    assembled package fails validation (both surfaced by the CLI).
    """
    cues = fetcher.fetch(meta.youtube_id)
    return ingest_from_cues(session, meta, cues, translator)
