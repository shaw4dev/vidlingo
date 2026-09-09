"""SM-2: how long until this word should be asked again.

Pure by construction. Nothing here imports sqlalchemy, fastapi or `app.*`, and
nothing reads a clock on its own — every input arrives as an argument and every
decision comes back as a return value. That is what lets the whole algorithm be
tested by writing down a table of (state, grade) -> state, with no fixtures, no
database and no mocked time.

Two functions, split deliberately:

    schedule()  decides HOW LONG, in days. Knows nothing about dates.
    due_at()    turns that into WHEN, given the user's local day boundary.

Keeping `schedule` free of a clock is what makes its tests exact rather than
approximate, and it is why there is no freezegun in this project's dev deps.

Why SM-2 and not FSRS: three state numbers that can be explained on a
whiteboard, and no training data required to work on day one. FSRS is the
deliberate follow-up — trained on the `review_log` rows this scheduler
produces, which is the point of recording the before/after of every grade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

# The three buttons the user actually sees, and the SM-2 quality values they
# stand for. SM-2 is specified over 0-5, but people cannot tell a 4 from a 5,
# and a scale nobody can apply consistently is noise dressed as precision.
# Three buttons, mapped onto the ends and the middle of the original scale.
Grade = Literal["forgot", "vague", "remembered"]

QUALITY: dict[Grade, int] = {
    "forgot": 1,
    "vague": 3,
    "remembered": 5,
}

# Ease is stored as an integer hundredth (250 == EF 2.50), not as a float.
#
# For the three quality values above, the SM-2 ease delta works out to exactly
# -54, -14 and +10 hundredths — whole numbers. Integer arithmetic therefore
# gives bit-identical results on SQLite and on Postgres, where floats would
# slowly drift apart between the dev database and production. A scheduling bug
# that only appears after months of accumulated rounding is close to
# undebuggable, so it is worth not being possible.
DEFAULT_EASE = 250
MIN_EASE = 130  # SM-2's floor: EF 1.3. Below this, intervals stop being useful.

# Display threshold only — never a scheduling input. A word crosses into
# "mastered" once it survives three weeks, and one `forgot` sends it straight
# back to "new", which is what "you never graduate out of the system" looks
# like in the UI.
MASTERED_DAYS = 21

# Intervals grow multiplicatively, so without a ceiling a well-known word ends
# up scheduled tens of thousands of years out — technically correct under the
# model, useless as a product. A year is the point where "check I still know
# this" stops being worth compounding further.
MAX_INTERVAL_DAYS = 365

# A lapsed card comes back later in the same session rather than tomorrow.
# Re-answering a word you just failed is the single highest-value moment in
# spaced repetition; deferring it to tomorrow wastes the failure.
LAPSE_RETRY = timedelta(minutes=10)


@dataclass(frozen=True)
class CardState:
    """Everything the scheduler needs to know about one word, for one user.

    Frozen because `schedule` returns a new state rather than mutating one —
    the caller then has both the before and the after, which is exactly what
    `review_log` records.
    """

    interval_days: int = 0
    ease: int = DEFAULT_EASE
    reps: int = 0
    lapses: int = 0


def schedule(state: CardState, quality: int) -> CardState:
    """Apply one grading. Returns the new state; the input is untouched.

    Note the asymmetry between the two things being tracked:

      `reps` is the rung of the ladder, and a lapse knocks it back to zero.
      `ease` is how hard this word has proven to be, and a lapse does *not*
      reset it — it lowers it, permanently.

    So a word you have forgotten once climbs the same ladder as a word you
    never missed, but with a smaller multiplier, and it keeps coming back more
    often for the rest of its life. That difference is the entire
    personalisation in SM-2. Drop `ease` from the carried state and every word
    behaves identically — at which point there is no algorithm, only a fixed
    table of intervals.
    """
    # The ease adjustment applies on every grading, successes and lapses alike.
    # For quality 5 / 3 / 1 this is exactly +10 / -14 / -54.
    delta = 10 - (5 - quality) * (8 + (5 - quality) * 2)
    ease = max(MIN_EASE, state.ease + delta)

    if quality < 3:
        # Forgotten. Back to the bottom of the ladder, and `interval_days = 0`
        # is the signal `due_at` reads as "later today", not "in zero days".
        return CardState(interval_days=0, ease=ease, reps=0, lapses=state.lapses + 1)

    reps = state.reps + 1
    if reps == 1:
        interval = 1
    elif reps == 2:
        interval = 3
    else:
        # Round half up with integer arithmetic. Python's built-in round() does
        # banker's rounding (round(0.5) == 0, round(1.5) == 2), which is a
        # surprising thing to find underneath a scheduling decision.
        grown = (state.interval_days * ease + 50) // 100

        # The floor matters more than it looks. At the ease floor with an
        # interval of 1 day, the multiplication alone gives 1 * 1.30 -> 1, and
        # the word is pinned at a one-day interval forever: the promise that
        # intervals always grow after a correct answer quietly stops holding,
        # and the card never leaves the daily queue. Requiring at least one
        # more day than last time makes growth unconditional.
        interval = max(state.interval_days + 1, grown)

    return CardState(
        interval_days=min(interval, MAX_INTERVAL_DAYS),
        ease=ease,
        reps=reps,
        lapses=state.lapses,
    )


def due_at(state: CardState, *, now: datetime, day_start: datetime) -> datetime:
    """When the card comes back, in UTC.

    Scheduled intervals are anchored to `day_start` — the beginning of the
    user's local day — rather than to `now`. A word due "in three days" is then
    available from the moment that day starts, instead of at whatever o'clock
    the previous review happened to be. Without this, reviewing at 9pm on
    Monday quietly makes every future review a 9pm appointment.

    A lapse is the exception: it has no day to be anchored to, because it is
    coming back within the current session.
    """
    if state.interval_days <= 0:
        return as_utc(now) + LAPSE_RETRY
    return as_utc(day_start) + timedelta(days=state.interval_days)


def day_start_utc(now: datetime, tz_offset_minutes: int) -> datetime:
    """Midnight at the start of the user's local day, expressed in UTC.

    `tz_offset_minutes` is minutes *east* of UTC — the negation of JavaScript's
    `Date.getTimezoneOffset()`, so Canberra in winter is +600.

    The offset comes from the browser on each request rather than from a column
    on `users`, because a stored offset needs a settings screen to ever be
    right, is wrong the moment the user travels, and is wrong twice a year
    under daylight saving. The browser knows the true answer for free, every
    time.
    """
    offset = timedelta(minutes=tz_offset_minutes)
    local = as_utc(now) + offset
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - offset


def mastery_for(state: CardState) -> str:
    """The label shown to the user. Derived, never stored.

    `mastery` used to be a free string the client PATCHed at will, which meant
    there was no authoritative answer to "does this user know this word".
    Deriving it from the schedule gives exactly one source of truth, and makes
    the label honest: it moves because the user's answers moved it.
    """
    if state.reps == 0:
        # Never passed, or passed and then forgotten. Both are "new" — which is
        # the point: mastery is reversible.
        return "new"
    if state.interval_days >= MASTERED_DAYS:
        return "mastered"
    return "learning"


def as_utc(value: datetime) -> datetime:
    """Coerce to an aware UTC datetime.

    SQLite hands back naive datetimes even for `DateTime(timezone=True)`
    columns, while Postgres returns aware ones. Everything stored is UTC, so a
    naive value is read as UTC rather than as local time — the alternative
    silently shifts every schedule by the developer's offset, and only in
    development.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)