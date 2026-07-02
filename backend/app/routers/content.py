"""Content API: browse lessons, fetch a lesson package, reverse word lookup.

Public (unauthenticated) read endpoints — content isn't user-specific.
`GET /words/{lemma}/occurrences` is what powers word->video reverse lookup (T16).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Lesson, Sentence, WordIndex
from app.db.session import get_session

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


# ---- endpoints -------------------------------------------------------------

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
def word_occurrences(lemma: str, db: Session = Depends(get_session)) -> OccurrencesResponse:
    key = lemma.strip().lower()
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
    return OccurrencesResponse(lemma=key, count=len(occurrences), occurrences=occurrences)
