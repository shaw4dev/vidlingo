"""SM-2 scheduler tests.

No fixtures, no database, no TestClient — `app.srs.sm2` imports none of that.
Every time-dependent assertion is exact because `now` and `day_start` are
parameters rather than something the module reads for itself.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.srs import sm2
from app.srs.sm2 import CardState


def _grade(state: CardState, grade: str) -> CardState:
    return sm2.schedule(state, sm2.QUALITY[grade])


# --- ease ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("grade", "expected_delta"),
    [("remembered", +10), ("vague", -14), ("forgot", -54)],
)
def test_ease_deltas_are_exact(grade: str, expected_delta: int) -> None:
    """The three deltas are whole hundredths; that is why ease is an int."""
    after = _grade(CardState(), grade)
    assert after.ease == sm2.DEFAULT_EASE + expected_delta


def test_ease_floors_and_stays_there() -> None:
    state = CardState()
    for _ in range(20):
        state = _grade(state, "forgot")
    assert state.ease == sm2.MIN_EASE
    assert _grade(state, "forgot").ease == sm2.MIN_EASE


def test_ease_adjusts_on_lapses_too() -> None:
    """SM-2 lowers ease on a failure — it does not merely reset the ladder."""
    before = CardState(interval_days=8, ease=280, reps=3)
    assert _grade(before, "forgot").ease == 280 - 54


# --- the interval ladder ---------------------------------------------------


def test_the_first_three_passes_walk_the_ladder() -> None:
    """1 day, then 3, then the multiplication takes over."""
    s0 = CardState()

    s1 = _grade(s0, "remembered")
    assert (s1.reps, s1.interval_days, s1.ease) == (1, 1, 260)

    s2 = _grade(s1, "remembered")
    assert (s2.reps, s2.interval_days, s2.ease) == (2, 3, 270)

    s3 = _grade(s2, "remembered")
    # ease becomes 280, so 3 * 2.80 = 8.4 -> 8
    assert (s3.reps, s3.interval_days, s3.ease) == (3, 8, 280)


def test_growth_is_unconditional_at_the_ease_floor() -> None:
    """The regression this guards: 1 * 1.30 rounds to 1, pinning the word.

    Without the `max(interval + 1, ...)` floor the interval never moves, the
    card never leaves the daily queue, and "intervals always grow" silently
    stops being true — for exactly the hardest words, which are the ones the
    user most needs to see progress on.
    """
    state = CardState(interval_days=1, ease=sm2.MIN_EASE, reps=5)
    assert _grade(state, "remembered").interval_days >= 2


def test_twenty_passes_grow_monotonically_up_to_the_cap() -> None:
    state = CardState()
    seen = []
    for _ in range(20):
        state = _grade(state, "remembered")
        seen.append(state.interval_days)

    capped_at = None
    for i in range(1, len(seen)):
        if seen[i] == sm2.MAX_INTERVAL_DAYS:
            capped_at = i
            break
        assert seen[i] > seen[i - 1], f"interval did not grow at step {i}: {seen}"

    assert capped_at is not None, f"never reached the cap in 20 passes: {seen}"
    assert all(v == sm2.MAX_INTERVAL_DAYS for v in seen[capped_at:])


def test_interval_never_exceeds_the_cap() -> None:
    state = CardState(interval_days=sm2.MAX_INTERVAL_DAYS, ease=300, reps=12)
    assert _grade(state, "remembered").interval_days == sm2.MAX_INTERVAL_DAYS


def test_vague_still_advances_but_costs_ease() -> None:
    """"模糊" is a pass: the word moves forward, but gets harder."""
    before = CardState(interval_days=8, ease=280, reps=3)
    after = _grade(before, "vague")
    assert after.reps == 4
    assert after.ease == 266
    assert after.interval_days > before.interval_days


# --- lapses ----------------------------------------------------------------


def test_a_lapse_resets_the_ladder_and_counts_itself() -> None:
    before = CardState(interval_days=21, ease=266, reps=4, lapses=0)
    after = _grade(before, "forgot")
    assert after.reps == 0
    assert after.interval_days == 0
    assert after.lapses == 1


def test_a_lapse_keeps_the_lowered_ease_into_the_next_pass() -> None:
    """The ladder resets; the difficulty estimate does not.

    A word forgotten once climbs the same rungs as one never missed, but with
    a permanently smaller multiplier — so it keeps coming back more often.
    This is the whole of SM-2's personalisation, and a plausible-looking bug
    (rebuilding state from defaults after a lapse) would erase it silently.
    """
    state = CardState(interval_days=21, ease=266, reps=4)
    lapsed = _grade(state, "forgot")
    assert lapsed.ease == 212

    recovered = _grade(lapsed, "remembered")
    assert recovered.reps == 1
    assert recovered.interval_days == 1
    assert recovered.ease == 222, "a lapse must not restore the default ease"

    # And the difference persists: same rung, smaller interval than a word
    # that has never been missed.
    pristine = _grade(_grade(_grade(CardState(), "remembered"), "remembered"), "remembered")
    scarred = _grade(_grade(recovered, "remembered"), "remembered")
    assert scarred.reps == pristine.reps == 3
    assert scarred.interval_days < pristine.interval_days


# --- mastery ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (CardState(), "new"),
        (CardState(interval_days=0, reps=0, lapses=3), "new"),
        (CardState(interval_days=1, reps=1), "learning"),
        (CardState(interval_days=sm2.MASTERED_DAYS - 1, reps=5), "learning"),
        (CardState(interval_days=sm2.MASTERED_DAYS, reps=5), "mastered"),
        (CardState(interval_days=365, reps=9), "mastered"),
    ],
)
def test_mastery_boundaries(state: CardState, expected: str) -> None:
    assert sm2.mastery_for(state) == expected


def test_mastery_is_reversible() -> None:
    """One "忘了" sends a mastered word back to "new" — never graduating,
    made visible."""
    mastered = CardState(interval_days=200, ease=280, reps=8)
    assert sm2.mastery_for(mastered) == "mastered"
    assert sm2.mastery_for(_grade(mastered, "forgot")) == "new"


# --- due dates -------------------------------------------------------------


def test_a_lapse_comes_back_within_the_session() -> None:
    now = datetime(2026, 9, 9, 21, 30, tzinfo=UTC)
    day_start = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)
    when = sm2.due_at(CardState(interval_days=0), now=now, day_start=day_start)
    assert when == now + sm2.LAPSE_RETRY


def test_scheduled_intervals_anchor_to_the_day_start_not_the_clock() -> None:
    """Reviewing at 9pm must not make every future review a 9pm appointment."""
    now = datetime(2026, 9, 9, 21, 30, tzinfo=UTC)
    day_start = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)
    when = sm2.due_at(CardState(interval_days=3, reps=3), now=now, day_start=day_start)
    assert when == day_start + timedelta(days=3)


def test_due_at_reads_naive_datetimes_as_utc() -> None:
    """SQLite returns naive datetimes; treating them as local would shift every
    schedule by the developer's own offset, and only in development."""
    naive = datetime(2026, 9, 9, 14, 0)
    aware = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)
    state = CardState(interval_days=2, reps=3)
    assert sm2.due_at(state, now=naive, day_start=naive) == sm2.due_at(
        state, now=aware, day_start=aware
    )


# --- local day boundaries --------------------------------------------------


@pytest.mark.parametrize("offset", [0, 600, 480, -300, 840, -720])
def test_day_start_is_local_midnight(offset: int) -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    start = sm2.day_start_utc(now, offset)
    local = start + timedelta(minutes=offset)
    assert (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0)
    assert start <= now
    assert now - start < timedelta(days=1)


def test_day_start_can_be_ahead_of_now_in_utc_terms() -> None:
    """Canberra (+600) just after local midnight: the local day began at
    14:00 UTC *the previous day*, so a naive `now.date()` would be a day out."""
    now = datetime(2026, 9, 9, 14, 30, tzinfo=UTC)  # 2026-09-10 00:30 local
    start = sm2.day_start_utc(now, 600)
    assert start == datetime(2026, 9, 9, 14, 0, tzinfo=UTC)


def test_two_users_either_side_of_the_dateline_get_different_days() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    assert sm2.day_start_utc(now, 840) != sm2.day_start_utc(now, -720)


def test_day_start_is_stable_across_a_local_day() -> None:
    """Every instant within one local day resolves to the same boundary —
    which is what makes the daily cap a day, and not a rolling window."""
    offset = 600
    base = sm2.day_start_utc(datetime(2026, 9, 9, 14, 0, tzinfo=UTC), offset)
    for hours in (0, 1, 6, 13, 23):
        later = base + timedelta(hours=hours, minutes=59)
        assert sm2.day_start_utc(later, offset) == base
