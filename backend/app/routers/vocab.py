"""Vocab API: per-user saved words/phrases. All endpoints require auth.

List/get responses embed the source sentence (+ its lesson/youtube_id) so the
app can jump straight back to where the word was seen (T15).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Lesson, Sentence, User, VocabItem
from app.db.session import get_session
from app.srs import sm2

router = APIRouter(prefix="/vocab", tags=["vocab"])

# Kept as a response type and as input validation, but no longer writable:
# mastery is derived from the review schedule (see `_to_out` and the PATCH
# handler below).
Mastery = Literal["new", "learning", "mastered"]


class SourceRef(BaseModel):
    sentence_id: str
    lesson_id: str
    lesson_title: str
    youtube_id: str | None
    idx: int
    start_ms: int
    # end_ms is what lets a caller play exactly this sentence and stop; the
    # review card needs it, and it is additive for existing clients.
    end_ms: int
    text_en: str
    text_zh: str


class VocabCreate(BaseModel):
    lemma: str = Field(min_length=1, max_length=64)
    surface: str | None = Field(default=None, max_length=128)
    source_sentence_id: str | None = None
    note: str | None = None


class VocabUpdate(BaseModel):
    # `mastery` stays declared even though it is rejected, and that is on
    # purpose: Pydantic ignores unknown keys, so deleting the field would make
    # an old client's {"mastery": "mastered"} return 200 OK and silently do
    # nothing -- the worst possible failure. Declared and refused, it gets an
    # error that names the replacement endpoint.
    mastery: Mastery | None = None
    note: str | None = None


class VocabItemOut(BaseModel):
    id: str
    lemma: str
    surface: str | None
    mastery: str            # derived from the schedule below, never stored
    note: str | None
    added_at: datetime
    due_at: datetime
    interval_days: int
    reps: int
    source: SourceRef | None


def _to_out(item: VocabItem, sentence: Sentence | None, lesson: Lesson | None) -> VocabItemOut:
    source = None
    if sentence is not None and lesson is not None:
        source = SourceRef(
            sentence_id=sentence.id,
            lesson_id=lesson.id,
            lesson_title=lesson.title,
            youtube_id=lesson.youtube_id,
            idx=sentence.idx,
            start_ms=sentence.start_ms,
            end_ms=sentence.end_ms,
            text_en=sentence.text_en,
            text_zh=sentence.text_zh,
        )
    state = sm2.CardState(
        interval_days=item.interval_days,
        ease=item.ease,
        reps=item.reps,
        lapses=item.lapses,
    )
    return VocabItemOut(
        id=item.id,
        lemma=item.lemma,
        surface=item.surface,
        mastery=sm2.mastery_for(state),
        note=item.note,
        added_at=item.added_at,
        due_at=sm2.as_utc(item.due_at),
        interval_days=item.interval_days,
        reps=item.reps,
        source=source,
    )


@router.get("", response_model=list[VocabItemOut])
def list_vocab(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[VocabItemOut]:
    stmt = (
        select(VocabItem, Sentence, Lesson)
        .outerjoin(Sentence, VocabItem.source_sentence_id == Sentence.id)
        .outerjoin(Lesson, Sentence.lesson_id == Lesson.id)
        .where(VocabItem.user_id == current.id)
        .order_by(VocabItem.added_at.desc())
    )
    return [_to_out(item, sentence, lesson) for item, sentence, lesson in db.execute(stmt).all()]


@router.post("", response_model=VocabItemOut, status_code=status.HTTP_201_CREATED)
def add_vocab(
    body: VocabCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> VocabItemOut:
    sentence = lesson = None
    if body.source_sentence_id is not None:
        sentence = db.get(Sentence, body.source_sentence_id)
        if sentence is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "source_sentence_id not found")
        lesson = db.get(Lesson, sentence.lesson_id)

    dup = db.scalar(
        select(VocabItem).where(
            VocabItem.user_id == current.id, VocabItem.lemma == body.lemma
        )
    )
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Word already in vocab")

    item = VocabItem(
        user_id=current.id,
        lemma=body.lemma,
        surface=body.surface,
        source_sentence_id=body.source_sentence_id,
        note=body.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item, sentence, lesson)


def _get_owned(item_id: str, current: User, db: Session) -> VocabItem:
    item = db.scalar(
        select(VocabItem).where(VocabItem.id == item_id, VocabItem.user_id == current.id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vocab item not found")
    return item


@router.patch("/{item_id}", response_model=VocabItemOut)
def update_vocab(
    item_id: str,
    body: VocabUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> VocabItemOut:
    item = _get_owned(item_id, current, db)
    if body.mastery is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "mastery is derived from review scheduling; grade the word via POST /review/grade",
        )
    if body.note is not None:
        item.note = body.note
    db.commit()
    db.refresh(item)

    sentence = db.get(Sentence, item.source_sentence_id) if item.source_sentence_id else None
    lesson = db.get(Lesson, sentence.lesson_id) if sentence else None
    return _to_out(item, sentence, lesson)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vocab(
    item_id: str,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    item = _get_owned(item_id, current, db)
    db.delete(item)
    db.commit()
