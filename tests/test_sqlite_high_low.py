"""Tests for SQLFunctions.updateHighLow() - covers the 3 fixes shipped 2026-07-20:

1. None-guard: comparing a sensor value against a stored max/min that is
   NULL in the database no longer raises TypeError, and self-heals by
   adopting the value as the new max/min.
2. Per-row isolation: one sensor's bad data doesn't prevent other sensors
   in the same call from updating.
3. Parameterized queries + isfinite guard: NaN/Infinity values are
   rejected with a warning rather than silently corrupting the table
   (or, pre-fix, crashing on malformed SQL text).
"""
import math

import pytest

from weatherflow2mqtt.const import TABLE_HIGH_LOW
from weatherflow2mqtt.sqlite import SQLFunctions


@pytest.fixture
def sql():
    """An SQLFunctions instance backed by an in-memory database with the
    high_low table created, ready for tests to seed rows into."""
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_HIGH_LOW)
    return instance


def seed_row(sql, sensorid, **columns):
    """Insert a high_low row with only the given columns set, leaving the
    rest NULL - mirrors real rows that predate a sensor being added to
    initializeHighLow(), or any other path that leaves max_day/min_day NULL."""
    cols = ", ".join(["sensorid", *columns.keys()])
    placeholders = ", ".join(["?"] * (1 + len(columns)))
    cursor = sql.connection.cursor()
    cursor.execute(
        f"INSERT INTO high_low({cols}) VALUES({placeholders})",
        (sensorid, *columns.values()),
    )
    sql.connection.commit()


def fetch_row(sql, sensorid):
    cursor = sql.connection.cursor()
    cursor.row_factory = None
    cursor.execute(
        "SELECT sensorid, latest, max_day, max_day_time, min_day, min_day_time "
        "FROM high_low WHERE sensorid = ?",
        (sensorid,),
    )
    row = cursor.fetchone()
    return dict(
        zip(
            ["sensorid", "latest", "max_day", "max_day_time", "min_day", "min_day_time"],
            row,
        )
    )


def test_null_max_min_self_heals(sql):
    """A row with NULL max_day/min_day adopts the first real value as both
    its new max and min, instead of raising TypeError (the original bug)."""
    seed_row(sql, "temperature")

    sql.updateHighLow({"temperature": 21.5})

    row = fetch_row(sql, "temperature")
    assert row["latest"] == 21.5
    assert row["max_day"] == 21.5
    assert row["min_day"] == 21.5
    assert row["max_day_time"] is not None
    assert row["min_day_time"] is not None


def test_normal_max_update(sql):
    """A value above the existing max updates max_day, leaves min_day alone."""
    seed_row(sql, "temperature", max_day=20.0, min_day=10.0)

    sql.updateHighLow({"temperature": 25.0})

    row = fetch_row(sql, "temperature")
    assert row["latest"] == 25.0
    assert row["max_day"] == 25.0
    assert row["min_day"] == 10.0


def test_normal_min_update(sql):
    """A value below the existing min updates min_day, leaves max_day alone."""
    seed_row(sql, "temperature", max_day=20.0, min_day=10.0)

    sql.updateHighLow({"temperature": 5.0})

    row = fetch_row(sql, "temperature")
    assert row["latest"] == 5.0
    assert row["max_day"] == 20.0
    assert row["min_day"] == 5.0


def test_value_within_range_updates_latest_only(sql):
    """A value that's neither a new max nor min still updates latest,
    without touching max_day/min_day/their timestamps."""
    seed_row(sql, "temperature", max_day=20.0, min_day=10.0)

    sql.updateHighLow({"temperature": 15.0})

    row = fetch_row(sql, "temperature")
    assert row["latest"] == 15.0
    assert row["max_day"] == 20.0
    assert row["min_day"] == 10.0
    assert row["max_day_time"] is None
    assert row["min_day_time"] is None


def test_no_data_for_sensor_leaves_row_untouched(sql):
    """A sensorid with no matching entry in the incoming data dict is
    left completely alone - no crash, no spurious update."""
    seed_row(sql, "temperature", max_day=20.0, min_day=10.0, latest=15.0)

    sql.updateHighLow({"humidity": 55.0})  # unrelated sensor

    row = fetch_row(sql, "temperature")
    assert row["latest"] == 15.0
    assert row["max_day"] == 20.0
    assert row["min_day"] == 10.0


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_value_rejected_not_stored(sql, bad_value):
    """NaN/Infinity is rejected (logged, not written) rather than silently
    corrupting the table - this is what parameterized queries would
    otherwise allow through, since SQLite happily stores non-finite floats."""
    seed_row(sql, "temperature", max_day=20.0, min_day=10.0, latest=15.0)

    sql.updateHighLow({"temperature": bad_value})

    row = fetch_row(sql, "temperature")
    assert row["latest"] == 15.0
    assert row["max_day"] == 20.0
    assert row["min_day"] == 10.0
    assert not math.isnan(row["max_day"])


def test_one_bad_sensor_does_not_block_others_in_same_cycle(sql):
    """The actual regression this session's fixes targeted: one sensor
    with a problem in the same update cycle must not prevent a different,
    perfectly valid sensor from updating."""
    seed_row(sql, "temperature", max_day=20.0, min_day=10.0)
    seed_row(sql, "humidity")  # NULL max/min - would have crashed pre-fix

    sql.updateHighLow(
        {
            "temperature": float("nan"),  # rejected
            "humidity": 55.0,  # must still succeed
        }
    )

    temp_row = fetch_row(sql, "temperature")
    assert temp_row["max_day"] == 20.0  # untouched by the rejected value

    humidity_row = fetch_row(sql, "humidity")
    assert humidity_row["latest"] == 55.0
    assert humidity_row["max_day"] == 55.0
    assert humidity_row["min_day"] == 55.0


def test_both_max_and_min_change_in_one_call(sql):
    """A NULL row where the single incoming value becomes both the new
    max and min simultaneously - exercises the SQL SET-clause builder's
    both-branches-fire path."""
    seed_row(sql, "pressure")

    sql.updateHighLow({"pressure": 1013.25})

    row = fetch_row(sql, "pressure")
    assert row["max_day"] == 1013.25
    assert row["min_day"] == 1013.25
    assert row["max_day_time"] is not None
    assert row["min_day_time"] is not None
