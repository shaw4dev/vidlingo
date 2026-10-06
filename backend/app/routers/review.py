"""Review API: today's queue, and grading a card. All endpoints require auth.

The queue is a query, not a table -- `due_at <= now()` over an index on
(user_id, due_at). Materialising it would add a second thing that can disagree
with the schedule, and buy nothing: the ordering is already free.

Cards embed everything the client needs to render and play them, so a session
of twenty costs three queries and no per-card follow-ups. The scheduling maths
lives in `app.srs.sm2`, which knows nothing about HTTP or the database; this
module is the part that reads rows, calls it, and writes rows back.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import (
    DictionaryEntry,
    Lesson,
    ReviewLog,
    Sentence,
    Token,
    User,
    VocabItem,
    WordIndex,
)
from app.db.session import get_session
from app.routers.vocab import SourceRef
from app.srs import sm2

router = APIRouter(prefix="/review", tags=["review"])

# Offsets range over UTC-12:00 to UTC+14:00. Bounding them keeps a nonsense
# value from producing an absurd day boundary, and therefore an absurd due date.
TZ_OFFSET = Query(default=0, ge=-720, le=840)

CardKind = Literal["cloze", "zh_prompt", "bare"]

# Below this, a sentence is too thin to host a cloze: punch out the target word
# and what remains does not determine an answer. "I ___ you" admits love, told,
# owe, miss, heard... so a learner who knows the word perfectly still cannot
# answer, and the 忘了 they press is noise in the schedule. 27% of the corpus
# is under this line, and the shortest sentences are a single word, where the
# blank *is* the whole sentence.
MIN_CLOZE_WORDS = 5


class ReviewSource(SourceRef):
    """The sentence the card is built on, plus where to punch holes in it."""

    blank_spans: list[tuple[int, int]]
    # True when this is not the line the word was saved from -- either it was
    # saved without one, or the original was too short to make a question. The
    # client says so, because "I don't remember meeting this word here" is
    # otherwise a confusing thing to hit mid-review.
    borrowed: bool


class ReviewDefinition(BaseModel):
    """Enough for the back of a card, from cache only.

    Deliberately no `senses`: it is the largest field, it is only wanted after
    the reveal, and the client already caches definitions in memory and in
    localStorage. Embedding a cache-only copy of everything would make the
    queue heavier and still fail for words nobody has looked up yet.
    """

    phonetic: str | None
    audio_url: str | None
    gloss_zh: str | None


class ReviewCardOut(BaseModel):
    vocab_item_id: str
    lemma: str
    surface: str | None
    note: str | None
    mastery: str
    due_at: datetime
    interval_days: int
    reps: int
    card_kind: CardKind
    source: ReviewSource | None
    definition: ReviewDefinition | None


class ReviewSummaryOut(BaseModel):
    day_start: datetime
    cap: int
    done_today: int
    due_total: int
    scheduled_today: int
    next_due_at: datetime | None


class ReviewQueueOut(ReviewSummaryOut):
    cards: list[ReviewCardOut]


class GradeIn(BaseModel):
    # Minted by the client once per card, not once per tap: a retry after a
    # timeout has to carry the same id or the idempotency guard never engages.
    client_event_id: str = Field(min_length=8, max_length=64)
    vocab_item_id: str
    grade: sm2.Grade
    latency_ms: int | None = Field(default=None, ge=0, le=600_000)
    tz_offset: int = Field(default=0, ge=-720, le=840)


class GradeOut(BaseModel):
    vocab_item_id: str
    grade: str
    mastery: str
    interval_days: int
    ease: int
    reps: int
    due_at: datetime
    duplicate: bool


# --- helpers ----------------------------------------------------------------


def _state_of(item: VocabItem) -> sm2.CardState:
    """The DB row as the scheduler's value object.

    This conversion, and the field-by-field write-back in `grade`, is the price
    of keeping `app.srs.sm2` free of SQLAlchemy. A dozen lines, in exchange for
    an algorithm that can be proved correct without a database.
    """
    return sm2.CardState(
        interval_days=item.interval_days,
        ease=item.ease,
        reps=item.reps,
        lapses=item.lapses,
    )


def _cap(limit: int | None) -> int:
    if limit is None:
        return settings.srs_daily_cap
    return max(1, min(limit, settings.srs_max_cap))


def _blank_spans(text_en: str, lemma: str, surface: str | None, tokens: list[Token]):
    """Where the answer sits in the sentence, so the client can hide it.

    Every occurrence is blanked, not just the first: leaving a second copy
    visible hands the learner the answer and makes the card unfailable, which
    makes the grade meaningless.

    The ladder exists because tokenisation is not perfect. The shipped corpus
    contains "let's" lemmatised to "let'", so a word can genuinely fail to
    match its own token, and the fallbacks are load-bearing rather than
    defensive decoration.
    """
    wanted = {lemma.lower()}
    if surface:
        wanted.add(surface.lower())

    spans = [(t.char_start, t.char_end) for t in tokens if t.lemma.lower() in wanted]
    if not spans:
        spans = [(t.char_start, t.char_end) for t in tokens if t.surface.lower() in wanted]
    if not spans:
        # No usable token: fall back to finding the word in the raw text.
        haystack = text_en.lower()
        for needle in ((surface or "").lower(), lemma.lower()):
            if not needle:
                continue
            found, at = [], haystack.find(needle)
            while at != -1:
                before_ok = at == 0 or not haystack[at - 1].isalnum()
                end = at + len(needle)
                after_ok = end == len(haystack) or not haystack[end].isalnum()
                if before_ok and after_ok:
                    found.append((at, end))
                at = haystack.find(needle, at + 1)
            if found:
                spans = found
                break

    return sorted(set(spans))


def _word_count(text: str) -> int:
    return len(text.split())


def _build_cards(
    rows: list[tuple[VocabItem, Sentence | None, Lesson | None]],
    db: Session,
) -> list[ReviewCardOut]:
    """Turn the queue rows into cards using three batched lookups, not N+1."""
    items = [item for item, _, _ in rows]

    # Two problems, one answer: a word saved from the word-detail page has no
    # sentence at all, and a word met in "Okay." has one too short to build a
    # question from. Both are solved by the reverse index -- the asset that
    # exists for exactly this question, "where else was this word said?".
    wanting = {
        item.lemma
        for item, sentence, _ in rows
        if sentence is None or _word_count(sentence.text_en) < MIN_CLOZE_WORDS
    }
    substitutes: dict[str, tuple[Sentence, Lesson]] = {}
    if wanting:
        stmt = (
            select(WordIndex.lemma, Sentence, Lesson)
            .join(Sentence, WordIndex.sentence_id == Sentence.id)
            .join(Lesson, WordIndex.lesson_id == Lesson.id)
            .where(WordIndex.lemma.in_(wanting))
            # Longest sentence wins; start_ms breaks ties so the same word
            # always draws the same example rather than shuffling between
            # sessions, which would read as a bug.
            .order_by(WordIndex.lemma, WordIndex.start_ms)
        )
        for lemma, sentence, lesson in db.execute(stmt).all():
            best = substitutes.get(lemma)
            if best is None or _word_count(sentence.text_en) > _word_count(best[0].text_en):
                substitutes[lemma] = (sentence, lesson)

    resolved: list[tuple[VocabItem, Sentence | None, Lesson | None, bool]] = []
    for item, sentence, lesson in rows:
        borrowed = False
        candidate = substitutes.get(item.lemma)
        if candidate is not None:
            words = _word_count(candidate[0].text_en)
            original = _word_count(sentence.text_en) if sentence is not None else 0
            # Only swap for something genuinely better. Substituting a decent
            # sentence would throw away the hook that makes this app different:
            # this is the scene *you* met the word in.
            if words >= MIN_CLOZE_WORDS and words > original:
                sentence, lesson = candidate
                borrowed = True
        resolved.append((item, sentence, lesson, borrowed))

    sentence_ids = {s.id for _, s, _, _ in resolved if s is not None}
    tokens_by_sentence: dict[str, list[Token]] = defaultdict(list)
    if sentence_ids:
        for tok in db.scalars(select(Token).where(Token.sentence_id.in_(sentence_ids))):
            tokens_by_sentence[tok.sentence_id].append(tok)

    # Cache reads only. Calling the dictionary provider here would mean up to
    # twenty network round trips -- and, with the LLM gloss configured, real
    # money -- inside a request the user is waiting on.
    lemmas = {i.lemma for i in items}
    definitions: dict[str, DictionaryEntry] = {}
    if lemmas:
        for entry in db.scalars(select(DictionaryEntry).where(DictionaryEntry.lemma.in_(lemmas))):
            definitions[entry.lemma] = entry

    cards: list[ReviewCardOut] = []
    for item, sentence, lesson, borrowed in resolved:
        source = None
        kind: CardKind = "bare"
        if sentence is not None and lesson is not None:
            spans = _blank_spans(
                sentence.text_en, item.lemma, item.surface, tokens_by_sentence[sentence.id]
            )
            # A cloze needs a hole to punch and enough sentence left around it
            # to determine the answer. Failing either, the front shows the
            # Chinese line alone and asks for the English: for a sentence this
            # short the translation *is* the whole question ("好吧。" -> Okay),
            # and a blank standing in for the entire sentence would add nothing.
            usable = spans and _word_count(sentence.text_en) >= MIN_CLOZE_WORDS
            kind = "cloze" if usable else "zh_prompt"
            source = ReviewSource(
                sentence_id=sentence.id,
                lesson_id=lesson.id,
                lesson_title=lesson.title,
                youtube_id=lesson.youtube_id,
                idx=sentence.idx,
                start_ms=sentence.start_ms,
                end_ms=sentence.end_ms,
                text_en=sentence.text_en,
                text_zh=sentence.text_zh,
                blank_spans=spans if usable else [],
                borrowed=borrowed,
            )

        entry = definitions.get(item.lemma)
        cards.append(
            ReviewCardOut(
                vocab_item_id=item.id,
                lemma=item.lemma,
                surface=item.surface,
                note=item.note,
                mastery=sm2.mastery_for(_state_of(item)),
                # Coerced because SQLite drops tzinfo on a DateTime(timezone=True)
                # column while Postgres keeps it. Serialising one naive and one
                # aware value for the same field is a difference that shows up
                # only in development, which is the worst place for it to hide.
                due_at=sm2.as_utc(item.due_at),
                interval_days=item.interval_days,
                reps=item.reps,
                card_kind=kind,
                source=source,
                definition=(
                    ReviewDefinition(
                        phonetic=entry.phonetic,
                        audio_url=entry.audio_url,
                        gloss_zh=entry.gloss_zh,
                    )
                    if entry
                    else None
                ),
            )
        )
    return cards


def _counts(user_id: str, day_start: datetime, now: datetime, cap: int, db: Session):
    # COUNT(DISTINCT ...), not COUNT(*): a card failed and re-shown ten minutes
    # later must not consume a second slot, or a bad session shrinks itself.
    done_today = (
        db.scalar(
            select(func.count(distinct(ReviewLog.vocab_item_id))).where(
                ReviewLog.user_id == user_id, ReviewLog.reviewed_at >= day_start
            )
        )
        or 0
    )
    due_total = (
        db.scalar(
            select(func.count())
            .select_from(VocabItem)
            .where(VocabItem.user_id == user_id, VocabItem.due_at <= now)
        )
        or 0
    )
    next_due_at = db.scalar(
        select(func.min(VocabItem.due_at)).where(
            VocabItem.user_id == user_id, VocabItem.due_at > now
        )
    )
    if next_due_at is not None:
        next_due_at = sm2.as_utc(next_due_at)
    remaining = max(0, cap - done_today)
    return done_today, due_total, next_due_at, remaining


# --- endpoints --------------------------------------------------------------


@router.get("/summary", response_model=ReviewSummaryOut)
def review_summary(
    tz_offset: int = TZ_OFFSET,
    limit: int | None = Query(default=None, ge=1),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> ReviewSummaryOut:
    """Two counts and no joins — for the header badge and the vocab banner.

    Separate from /queue so the first screen never pays for twenty cards it is
    not going to show.
    """
    now = datetime.now(UTC)
    day_start = sm2.day_start_utc(now, tz_offset)
    cap = _cap(limit)
    done_today, due_total, next_due_at, remaining = _counts(current.id, day_start, now, cap, db)
    return ReviewSummaryOut(
        day_start=day_start,
        cap=cap,
        done_today=done_today,
        due_total=due_total,
        scheduled_today=min(remaining, due_total),
        next_due_at=next_due_at,
    )


@router.get("/queue", response_model=ReviewQueueOut)
def review_queue(
    tz_offset: int = TZ_OFFSET,
    limit: int | None = Query(default=None, ge=1),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> ReviewQueueOut:
    now = datetime.now(UTC)
    day_start = sm2.day_start_utc(now, tz_offset)
    cap = _cap(limit)
    done_today, due_total, next_due_at, remaining = _counts(current.id, day_start, now, cap, db)

    rows: list[tuple[VocabItem, Sentence | None, Lesson | None]] = []
    if remaining:
        stmt = (
            select(VocabItem, Sentence, Lesson)
            .outerjoin(Sentence, VocabItem.source_sentence_id == Sentence.id)
            .outerjoin(Lesson, Sentence.lesson_id == Lesson.id)
            .where(VocabItem.user_id == current.id, VocabItem.due_at <= now)
            # `added_at` breaks ties deterministically. It matters more than it
            # looks: the migration gave every pre-existing row the same due_at,
            # so without it the backlog order is whatever the storage engine
            # feels like, and it can change between page loads.
            .order_by(VocabItem.due_at.asc(), VocabItem.added_at.asc())
            .limit(remaining)
        )
        rows = list(db.execute(stmt).all())

    return ReviewQueueOut(
        day_start=day_start,
        cap=cap,
        done_today=done_today,
        due_total=due_total,
        scheduled_today=min(remaining, due_total),
        next_due_at=next_due_at,
        cards=_build_cards(rows, db),
    )


@router.post("/grade", response_model=GradeOut)
def grade(
    body: GradeIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> GradeOut:
    """Apply one answer: advance the schedule and record what happened.

    200, not 201: the response is the new schedule, not a resource the client
    goes on to address.
    """
    item = db.scalar(
        select(VocabItem).where(
            VocabItem.id == body.vocab_item_id, VocabItem.user_id == current.id
        )
    )
    if item is None:
        # 404 rather than 403 for another user's row, matching the vocab
        # router: whether someone else's id exists is not ours to disclose.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vocab item not found")

    now = datetime.now(UTC)
    day_start = sm2.day_start_utc(now, body.tz_offset)
    quality = sm2.QUALITY[body.grade]

    before = _state_of(item)
    after = sm2.schedule(before, quality)
    next_due = sm2.due_at(after, now=now, day_start=day_start)

    was_due_at = item.due_at
    item.interval_days = after.interval_days
    item.ease = after.ease
    item.reps = after.reps
    item.lapses = after.lapses
    item.due_at = next_due
    item.last_reviewed_at = now

    db.add(
        ReviewLog(
            user_id=current.id,
            client_event_id=body.client_event_id,
            vocab_item_id=item.id,
            lemma=item.lemma,
            grade=body.grade,
            quality=quality,
            interval_before=before.interval_days,
            ease_before=before.ease,
            reps_before=before.reps,
            interval_after=after.interval_days,
            ease_after=after.ease,
            reps_after=after.reps,
            lapses_after=after.lapses,
            due_at=was_due_at,
            reviewed_at=now,
            next_due_at=next_due,
            latency_ms=body.latency_ms,
            tz_offset_minutes=body.tz_offset,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        # This event was already applied. Insert-then-catch rather than
        # select-then-insert, because the latter has a race window and this has
        # none: the rollback also discards the vocab_items update above, so a
        # concurrent duplicate cannot advance the schedule twice.
        db.rollback()
        return _replay(body, db)

    return GradeOut(
        vocab_item_id=item.id,
        grade=body.grade,
        mastery=sm2.mastery_for(after),
        interval_days=after.interval_days,
        ease=after.ease,
        reps=after.reps,
        due_at=next_due,
        duplicate=False,
    )


def _replay(body: GradeIn, db: Session) -> GradeOut:
    """Answer a repeated submission from the log, without rescheduling.

    This is why the log stores the state it produced as well as the state it
    started from: a replay needs no recomputation and cannot drift from what
    the first attempt actually did.
    """
    logged = db.scalar(
        select(ReviewLog).where(
            ReviewLog.client_event_id == body.client_event_id,
            ReviewLog.vocab_item_id == body.vocab_item_id,
        )
    )
    if logged is None:  # pragma: no cover - the unique key fired, so a row exists
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate review event")

    state = sm2.CardState(
        interval_days=logged.interval_after,
        ease=logged.ease_after,
        reps=logged.reps_after,
        lapses=logged.lapses_after,
    )
    return GradeOut(
        vocab_item_id=body.vocab_item_id,
        grade=logged.grade,
        mastery=sm2.mastery_for(state),
        interval_days=logged.interval_after,
        ease=logged.ease_after,
        reps=logged.reps_after,
        due_at=sm2.as_utc(logged.next_due_at),
        duplicate=True,
    )
