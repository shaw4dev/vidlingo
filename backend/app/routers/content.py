"""Content API: browse lessons, fetch a lesson package, reverse word lookup.

Public (unauthenticated) read endpoints — content isn't user-specific.
`GET /words/{lemma}/occurrences` is what powers word->video reverse lookup (T16).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.content.backfill import MIN_COVERAGE, BackfillTrigger, get_backfill_trigger
from app.content.dictionary import (
    DictionaryError,
    DictionaryProvider,
    GlossProvider,
    get_dictionary_provider,
    get_gloss_provider,
    lookup_definition,
)
from app.db.models import Clip, Lesson, Sentence, WordIndex
from app.db.session import get_session
from app.pipeline.nlp import lemmatize

router = APIRouter(tags=["content"])


# ---- response schemas ------------------------------------------------------

class LessonSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    youtube_id: str | None
    title: str
    theme: str
    difficulty: str | None
    duration_ms: int
    source: str | None


class TokenOut(BaseModel):
    char_span: tuple[int, int]
    surface: str
    lemma: str
    pos: str | None
    dict_ref: str | None


class SentenceOut(BaseModel):
    id: str
    idx: int
    start_ms: int
    end_ms: int
    text_en: str
    text_zh: str
    difficulty: str
    tokens: list[TokenOut]


class LessonDetail(LessonSummary):
    sentences: list[SentenceOut]


class Occurrence(BaseModel):
    lesson_id: str
    youtube_id: str | None
    lesson_title: str
    sentence_id: str
    idx: int
    start_ms: int
    text_en: str
    text_zh: str


class OccurrencesResponse(BaseModel):
    lemma: str
    count: int
    occurrences: list[Occurrence]


class SenseOut(BaseModel):
    pos: str | None
    definition: str
    example: str | None


class DefinitionResponse(BaseModel):
    """What the word card renders (T13). `gloss_zh` is present only when a
    Chinese gloss provider is configured; the card degrades to English senses."""

    lemma: str
    phonetic: str | None
    audio_url: str | None
    gloss_zh: str | None
    senses: list[SenseOut]
    provider: str


class FeedClip(BaseModel):
    """One playable feed item: a 30-90s window of a lesson. The client embeds
    the youtube_id and plays [start_ms, end_ms)."""

    clip_id: str
    lesson_id: str
    youtube_id: str | None
    title: str
    theme: str
    difficulty: str
    start_ms: int
    end_ms: int
    duration_ms: int
    text_en: str


class FeedResponse(BaseModel):
    clips: list[FeedClip]
    next_offset: int | None  # pass back as ?offset= for the next page; null at end


# ---- endpoints -------------------------------------------------------------

@router.get("/feed", response_model=FeedResponse)
def feed(
    theme: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> FeedResponse:
    """The front-page clip feed (Feature A).

    v0 ranking is a deterministic placeholder: order by clip position
    (`start_idx`) then lesson recency, which interleaves lessons — the feed
    shows each lesson's opening clip before its later ones, so a short library
    doesn't return one lesson's clips back-to-back. Real personalization
    (watch history, vocab level, engagement) replaces this later. Stable order
    makes offset paging safe.
    """
    stmt = select(Clip, Lesson).join(Lesson, Clip.lesson_id == Lesson.id)
    if theme:
        stmt = stmt.where(Lesson.theme == theme)
    if difficulty:
        stmt = stmt.where(Clip.difficulty == difficulty)
    stmt = stmt.order_by(Clip.start_idx, Lesson.created_at.desc(), Clip.lesson_id)
    stmt = stmt.offset(offset).limit(limit + 1)  # +1 to detect a next page

    rows = db.execute(stmt).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    clips = [
        FeedClip(
            clip_id=clip.id,
            lesson_id=lesson.id,
            youtube_id=lesson.youtube_id,
            title=lesson.title,
            theme=lesson.theme,
            difficulty=clip.difficulty,
            start_ms=clip.start_ms,
            end_ms=clip.end_ms,
            duration_ms=clip.duration_ms,
            text_en=clip.text_en,
        )
        for clip, lesson in rows
    ]
    return FeedResponse(clips=clips, next_offset=offset + limit if has_more else None)


@router.get("/lessons", response_model=list[LessonSummary])
def list_lessons(
    theme: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    db: Session = Depends(get_session),
) -> list[Lesson]:
    stmt = select(Lesson)
    if theme:
        stmt = stmt.where(Lesson.theme == theme)
    if difficulty:
        stmt = stmt.where(Lesson.difficulty == difficulty)
    stmt = stmt.order_by(Lesson.title)
    return list(db.scalars(stmt).all())


@router.get("/lessons/{lesson_id}", response_model=LessonDetail)
def get_lesson(lesson_id: str, db: Session = Depends(get_session)) -> LessonDetail:
    lesson = db.scalars(
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .options(selectinload(Lesson.sentences).selectinload(Sentence.tokens))
    ).first()
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")

    return LessonDetail(
        id=lesson.id,
        provider=lesson.provider,
        youtube_id=lesson.youtube_id,
        title=lesson.title,
        theme=lesson.theme,
        difficulty=lesson.difficulty,
        duration_ms=lesson.duration_ms,
        source=lesson.source,
        sentences=[
            SentenceOut(
                id=s.id,
                idx=s.idx,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                text_en=s.text_en,
                text_zh=s.text_zh,
                difficulty=s.difficulty,
                tokens=[
                    TokenOut(
                        char_span=(t.char_start, t.char_end),
                        surface=t.surface,
                        lemma=t.lemma,
                        pos=t.pos,
                        dict_ref=t.dict_ref,
                    )
                    for t in s.tokens
                ],
            )
            for s in lesson.sentences
        ],
    )


@router.get("/words/{lemma}/occurrences", response_model=OccurrencesResponse)
def word_occurrences(
    lemma: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
    trigger: BackfillTrigger = Depends(get_backfill_trigger),
) -> OccurrencesResponse:
    # Lemmatize the input so tapping any surface form ("running", "goes") resolves
    # to the stored lemma ("run", "go") — the index holds lemmas, not surfaces.
    key = lemmatize(lemma.strip().lower())
    stmt = (
        select(WordIndex, Sentence, Lesson)
        .join(Sentence, WordIndex.sentence_id == Sentence.id)
        .join(Lesson, WordIndex.lesson_id == Lesson.id)
        .where(func.lower(WordIndex.lemma) == key)
        .order_by(Lesson.title, WordIndex.start_ms)
    )
    rows = db.execute(stmt).all()
    occurrences = [
        Occurrence(
            lesson_id=lesson.id,
            youtube_id=lesson.youtube_id,
            lesson_title=lesson.title,
            sentence_id=sentence.id,
            idx=sentence.idx,
            start_ms=wi.start_ms,
            text_en=sentence.text_en,
            text_zh=sentence.text_zh,
        )
        for wi, sentence, lesson in rows
    ]
    # Under-covered word -> schedule a background backfill so it has more
    # fragments next time. Non-blocking: this response ships what exists now.
    if len(occurrences) < MIN_COVERAGE:
        trigger(background_tasks, key)
    return OccurrencesResponse(lemma=key, count=len(occurrences), occurrences=occurrences)


@router.get("/words/{lemma}/definition", response_model=DefinitionResponse)
def word_definition(
    lemma: str,
    db: Session = Depends(get_session),
    provider: DictionaryProvider = Depends(get_dictionary_provider),
    gloss_provider: GlossProvider | None = Depends(get_gloss_provider),
) -> DefinitionResponse:
    """Dictionary entry for a tapped word (T13 word card).

    Tries the lemma first, then the raw surface form — our v0 lemmatizer is
    rule-based and mangles some words ("series" -> "sery"), and the surface
    form is what the dictionary actually indexes in those cases.
    """
    surface = lemma.strip().lower()
    key = lemmatize(surface)
    try:
        definition = lookup_definition(db, [key, surface], provider, gloss_provider)
    except DictionaryError as exc:
        # The word may well exist; we just couldn't reach the dictionary. Say so
        # rather than claiming it's unknown.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No dictionary entry for '{key}'")

    return DefinitionResponse(
        lemma=definition.lemma,
        phonetic=definition.phonetic,
        audio_url=definition.audio_url,
        gloss_zh=definition.gloss_zh,
        senses=[
            SenseOut(pos=s.pos, definition=s.definition, example=s.example)
            for s in definition.senses
        ],
        provider=definition.provider,
    )
