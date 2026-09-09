"""ORM models mirroring the LessonPackage contract (architecture.md §5.2).

Key relationships:
    Lesson 1--* Sentence 1--* Token
    WordIndex: lemma -> (sentence, lesson, start_ms)  -> powers reverse lookup (T05/T16)
    User 1--* VocabItem -> source Sentence
    VocabItem 1--* ReviewLog  -> spaced repetition state + its audit trail (T19)

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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.srs import sm2  # scheduling constants; sm2 imports nothing from app


def _uuid() -> str:
    return uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Nullable because accounts predate it (the demo user has none) and because
    # the column is unique — a shared empty string would collide on the second
    # row. New registrations require one: it is the only channel through which
    # an account can ever be recovered.
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
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
    clips: Mapped[list[Clip]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan", order_by="Clip.start_idx"
    )
    # Needed for ORM-level cascade, not just navigation: load_package() re-ingests
    # a lesson by deleting and reinserting it, and session.delete() only follows
    # relationships. The FK's ondelete="CASCADE" doesn't cover it — SQLite ignores
    # foreign keys unless PRAGMA foreign_keys is on. Without this, re-ingest left
    # the old rows behind, and since sentence ids are deterministic they weren't
    # even orphans — just silent duplicates inflating every reverse lookup.
    word_index: Mapped[list[WordIndex]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan"
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

    lesson: Mapped[Lesson] = relationship(back_populates="word_index")


class Clip(Base):
    """A 30-90s window of a lesson (a contiguous sentence range) — the unit the
    front-page feed serves. Generated from a lesson's sentences at ingest time
    (see app.pipeline.clips); one Lesson yields many Clips."""

    __tablename__ = "clips"
    __table_args__ = (UniqueConstraint("lesson_id", "start_idx", "end_idx"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True
    )
    start_idx: Mapped[int] = mapped_column(Integer)  # first sentence idx (inclusive)
    end_idx: Mapped[int] = mapped_column(Integer)  # last sentence idx (inclusive)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(8), index=True)
    text_en: Mapped[str] = mapped_column(Text)  # concatenated preview of the window

    lesson: Mapped[Lesson] = relationship(back_populates="clips")


class WordSearch(Base):
    """Quota cache for on-demand word backfill: records that we already searched
    the API for a lemma, so a repeated miss doesn't re-spend 100 quota units.
    See app.pipeline.sourcing.backfill_word."""

    __tablename__ = "word_searches"

    lemma: Mapped[str] = mapped_column(String(64), primary_key=True)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ingested_count: Mapped[int] = mapped_column(Integer, default=0)


class DictionaryEntry(Base):
    """Cache of looked-up word definitions (T13 word card).

    The dictionary itself is an external provider (see app.content.dictionary);
    this table means we hit it once per lemma, ever. `senses` holds the
    provider's sense list as JSON text so the shape can evolve without a
    migration. A row is only written for a successful lookup — misses aren't
    cached, so a word gains an entry as soon as the provider learns it.
    """

    __tablename__ = "dictionary_entries"

    lemma: Mapped[str] = mapped_column(String(64), primary_key=True)
    phonetic: Mapped[str | None] = mapped_column(String(64))
    audio_url: Mapped[str | None] = mapped_column(String(512))
    gloss_zh: Mapped[str | None] = mapped_column(Text)
    senses: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    provider: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VocabItem(Base):
    """A word one user saved, plus where its review schedule currently stands.

    The scheduling columns are the live state; `review_log` is the history that
    produced them. State could be replayed from the log, but the queue query
    runs on every request, so it is kept materialised here and the log is kept
    for audit and for training.

    There is deliberately no `mastery` column. It used to be a free string the
    client PATCHed at will, which left no authoritative answer to "does this
    user know this word". It is now derived from `interval_days`/`reps` by
    `app.srs.sm2.mastery_for`, so there is exactly one source of truth.
    """

    __tablename__ = "vocab_items"
    __table_args__ = (
        UniqueConstraint("user_id", "lemma"),
        # The review queue is this index and nothing else: no queue table, just
        # `WHERE user_id = ? AND due_at <= now() ORDER BY due_at LIMIT n`.
        # Materialising a queue would only add ways for it to disagree with the
        # schedule.
        Index("ix_vocab_items_user_due", "user_id", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lemma: Mapped[str] = mapped_column(String(64))
    surface: Mapped[str | None] = mapped_column(String(128))
    source_sentence_id: Mapped[str | None] = mapped_column(
        ForeignKey("sentences.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- spaced repetition state (app/srs/sm2.py) ---------------------------
    # A newly saved word is due immediately: it was saved because the user
    # didn't know it. `server_default` as well as a Python default, so a raw
    # INSERT outside the ORM cannot leave the queue key NULL.
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now()
    )
    interval_days: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # SM-2's ease factor x100 (250 == EF 2.50). Integer, not float, so the
    # arithmetic is bit-identical on SQLite and Postgres -- see sm2.py.
    ease: Mapped[int] = mapped_column(
        Integer, server_default=str(sm2.DEFAULT_EASE), default=sm2.DEFAULT_EASE
    )
    reps: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Lifetime lapse count. Not read by SM-2; kept because "how often was this
    # forgotten" is the strongest single feature for the difficulty model in
    # architecture.md §7, and it cannot be reconstructed once lost.
    lapses: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="vocab_items")


class ReviewLog(Base):
    """One grading, recorded once and never touched again.

    Append-only: the app never UPDATEs or DELETEs a row here. Two jobs:

    1. Idempotency. A retried submission (flaky network, impatient tap) must
       not advance the schedule twice, so the client mints an id per card and
       the unique constraint below makes a double-apply impossible.
    2. Training data. Each row is a (what we predicted, what happened) pair —
       the state before, the answer, and the state it produced. That is the
       supervision signal for the difficulty model in architecture.md §7, and
       the reason to record FSRS's headline feature now rather than later:
       `reviewed_at - due_at` is how overdue the card was when answered.

    Storing both sides means a row is interpretable on its own, with no join
    and no replay from the beginning of time.
    """

    __tablename__ = "review_log"
    __table_args__ = (
        # The idempotency guarantee. Scoped per user so two clients cannot
        # collide, however they generate ids.
        UniqueConstraint("user_id", "client_event_id"),
        # "How many did I do today" on every queue request.
        Index("ix_review_log_user_reviewed", "user_id", "reviewed_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_event_id: Mapped[str] = mapped_column(String(64))

    # SET NULL, not CASCADE, and so nullable: deleting a word must not destroy
    # the evidence of having studied it. A log a user action can retroactively
    # rewrite is not a log.
    vocab_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("vocab_items.id", ondelete="SET NULL"), index=True
    )
    # Denormalised so the row still says which word it was after the FK above
    # goes NULL.
    lemma: Mapped[str] = mapped_column(String(64))

    # Both the button pressed and the number fed to SM-2. If the mapping ever
    # changes, old rows still record what the user actually chose.
    grade: Mapped[str] = mapped_column(String(16))
    quality: Mapped[int] = mapped_column(Integer)

    interval_before: Mapped[int] = mapped_column(Integer)
    ease_before: Mapped[int] = mapped_column(Integer)
    reps_before: Mapped[int] = mapped_column(Integer)
    interval_after: Mapped[int] = mapped_column(Integer)
    ease_after: Mapped[int] = mapped_column(Integer)
    reps_after: Mapped[int] = mapped_column(Integer)
    lapses_after: Mapped[int] = mapped_column(Integer)

    # When it was scheduled for vs. when it was actually answered. The gap is
    # the overdue-ness feature; nullable only for defensive robustness.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Stored so an idempotent replay can answer from the log without
    # recomputing the schedule.
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Time from the card front appearing to the button press. Hesitating before
    # "remembered" is not the same as answering instantly. Nullable: a reload
    # loses the start time.
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # The offset the client claimed, so "which local day was this?" stays
    # reconstructible offline and a wrong clock is auditable rather than silent.
    tz_offset_minutes: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
