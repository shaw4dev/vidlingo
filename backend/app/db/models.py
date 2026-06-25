"""ORM models mirroring the LessonPackage contract (architecture.md §5.2).

Key relationships:
    Lesson 1--* Sentence 1--* Token
    WordIndex: lemma -> (sentence, lesson, start_ms)  -> powers reverse lookup (T05/T16)
    User 1--* VocabItem -> source Sentence

IDs: lessons keep their package id (e.g. "vid_smalltalk_001"); sentences use a
global id "<lesson_id>:<local_id>" so per-package ids ("s1") never collide across
lessons. Other rows use uuid4 hex.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vocab_items: Mapped[list[VocabItem]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), default="youtube")
    youtube_id: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    theme: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str | None] = mapped_column(String(255))
    license_tag: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str | None] = mapped_column(String(8), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    package_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sentences: Mapped[list[Sentence]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", order_by="Sentence.idx"
    )


class Sentence(Base):
    __tablename__ = "sentences"
    __table_args__ = (UniqueConstraint("lesson_id", "idx"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text_en: Mapped[str] = mapped_column(Text)
    text_zh: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(8))

    lesson: Mapped[Lesson] = relationship(back_populates="sentences")
    tokens: Mapped[list[Token]] = relationship(
        back_populates="sentence", cascade="all, delete-orphan"
    )


class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    sentence_id: Mapped[str] = mapped_column(
        ForeignKey("sentences.id", ondelete="CASCADE"), index=True
    )
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    surface: Mapped[str] = mapped_column(String(128))
    lemma: Mapped[str] = mapped_column(String(64), index=True)
    pos: Mapped[str | None] = mapped_column(String(16))
    dict_ref: Mapped[str | None] = mapped_column(String(128))

    sentence: Mapped[Sentence] = relationship(back_populates="tokens")


class WordIndex(Base):
    """Inverted index: a lemma -> where it occurs. Powers word->video lookup."""

    __tablename__ = "word_index"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lemma: Mapped[str] = mapped_column(String(64), index=True)
    sentence_id: Mapped[str] = mapped_column(ForeignKey("sentences.id", ondelete="CASCADE"))
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    start_ms: Mapped[int] = mapped_column(Integer)


class VocabItem(Base):
    __tablename__ = "vocab_items"
    __table_args__ = (UniqueConstraint("user_id", "lemma"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lemma: Mapped[str] = mapped_column(String(64))
    surface: Mapped[str | None] = mapped_column(String(128))
    source_sentence_id: Mapped[str | None] = mapped_column(
        ForeignKey("sentences.id", ondelete="SET NULL")
    )
    mastery: Mapped[str] = mapped_column(String(16), default="new")
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="vocab_items")
