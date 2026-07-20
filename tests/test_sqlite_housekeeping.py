"""Tests for dailyHousekeeping() - the daily/weekly/monthly/yearly rollover
job. Covers the deterministic parts (no date-boundary logic involved) plus
one year-boundary test using a real relative time offset (400 days ago is
always a different calendar year from "now", no clock-mocking needed).

NOT covered: the month/week boundary branches (strftime('%m'/'%W', ...)
comparisons). Those are testable the same way as the year case, but week
boundaries in particular (SQLite's %W week-number format resets at Jan 1
regardless of what day of the week that falls on) have enough edge-case
subtlety near year boundaries that a naive relative-offset test could be
flaky depending on which day of the week "now" happens to be. Left as a
known gap rather than force a low-value/flaky test.
"""
import time

import pytest

from weatherflow2mqtt.const import TABLE_HIGH_LOW, TABLE_LIGHTNING, TABLE_PRESSURE
from weatherflow2mqtt.sqlite import SQLFunctions

YEAR_IN_SECONDS = 400 * 24 * 60 * 60  # comfortably >1 calendar year


@pytest.fixture
def sql():
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_HIGH_LOW)
    instance.create_table(TABLE_PRESSURE)
    instance.create_table(TABLE_LIGHTNING)
    return instance


def seed_row(sql, sensorid, **columns):
    cols = ", ".join(["sensorid", *columns.keys()])
    placeholders = ", ".join(["?"] * (1 + len(columns)))
    cursor = sql.connection.cursor()
    cursor.execute(
        f"INSERT INTO high_low({cols}) VALUES({placeholders})",
        (sensorid, *columns.values()),
    )
    sql.connection.commit()


def fetch(sql, sensorid, *cols):
    cursor = sql.connection.cursor()
    cursor.execute(
        f"SELECT {', '.join(cols)} FROM high_low WHERE sensorid = ?", (sensorid,)
    )
    row = cursor.fetchone()
    return dict(zip(cols, row))


def test_old_pressure_and_lightning_rows_purged(sql):
    cursor = sql.connection.cursor()
    old_time = time.time() - 4 * 60 * 60  # older than PRESSURE_TREND_TIMER + buffer
    cursor.execute("INSERT INTO pressure(timestamp, pressure) VALUES(?, ?)", (old_time, 1010.0))
    cursor.execute("INSERT INTO pressure(timestamp, pressure) VALUES(?, ?)", (time.time(), 1013.0))
    cursor.execute("INSERT INTO lightning(timestamp) VALUES(?)", (old_time,))
    cursor.execute("INSERT INTO lightning(timestamp) VALUES(?)", (time.time(),))
    sql.connection.commit()

    sql.dailyHousekeeping()

    cursor.execute("SELECT COUNT(*) FROM pressure")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM lightning")
    assert cursor.fetchone()[0] == 1


def test_all_time_max_updates_when_day_exceeds_it(sql):
    seed_row(sql, "temperature", max_day=30.0, max_day_time=time.time(), max_all=25.0)

    sql.dailyHousekeeping()

    row = fetch(sql, "temperature", "max_all", "max_all_time")
    assert row["max_all"] == 30.0
    assert row["max_all_time"] is not None


def test_all_time_min_requires_min_day_time_not_null(sql):
    """The guard 'min_day_time IS NOT NULL' means a row that's never
    actually recorded a min (min_day_time still NULL) must not overwrite
    min_all even if min_day looks numerically lower."""
    seed_row(sql, "temperature", min_day=-9999, min_day_time=None, min_all=5.0)

    sql.dailyHousekeeping()

    row = fetch(sql, "temperature", "min_all")
    assert row["min_all"] == 5.0  # unchanged, guard correctly blocked the update


def test_yesterday_captures_pre_reset_day_values(sql):
    """Statement ordering matters: yesterday must copy the day's values
    BEFORE the day-reset statements overwrite them - this test would catch
    a future reordering bug."""
    seed_row(sql, "temperature", max_day=28.0, min_day=15.0, latest=20.0)

    sql.dailyHousekeeping()

    row = fetch(sql, "temperature", "max_yday", "min_yday", "max_day", "min_day")
    assert row["max_yday"] == 28.0
    assert row["min_yday"] == 15.0
    # And the day values themselves got reset to latest in the same call.
    assert row["max_day"] == 20.0
    assert row["min_day"] == 20.0


def test_day_reset_both_max_and_min_when_min_day_nonzero(sql):
    seed_row(sql, "temperature", max_day=28.0, min_day=15.0, latest=19.5)

    sql.dailyHousekeeping()

    row = fetch(sql, "temperature", "max_day", "min_day")
    assert row["max_day"] == 19.5
    assert row["min_day"] == 19.5


def test_day_reset_only_max_when_min_day_already_zero(sql):
    """Sensors like illuminance/uv start their day at min_day=0 - the reset
    only needs to zero max_day, min_day is already correct."""
    seed_row(sql, "illuminance", max_day=45000, min_day=0, latest=100)

    sql.dailyHousekeeping()

    row = fetch(sql, "illuminance", "max_day", "min_day")
    assert row["max_day"] == 0
    assert row["min_day"] == 0  # untouched, was already 0


def test_year_rollover_resets_from_last_years_data(sql):
    """max_day_time from >1 year ago means the stored max_year is stale -
    dailyHousekeeping() should reset max_year/min_year from latest, not
    carry the old year's value forward."""
    last_year_ts = time.time() - YEAR_IN_SECONDS
    seed_row(
        sql,
        "temperature",
        max_day=22.0,
        max_day_time=last_year_ts,
        min_day=10.0,
        min_day_time=last_year_ts,
        max_year=35.0,  # stale value from last year
        max_year_time=last_year_ts,
        latest=18.0,
    )

    sql.dailyHousekeeping()

    row = fetch(sql, "temperature", "max_year", "min_year")
    assert row["max_year"] == 18.0  # reset from latest, not carried over as 35.0
    assert row["min_year"] == 18.0


def test_year_values_carry_forward_within_same_year(sql):
    """max_day_time from earlier today (same year) means the normal
    'is this day's max bigger than the year's max' comparison should run
    instead of the year-rollover reset."""
    seed_row(
        sql,
        "temperature",
        max_day=30.0,
        max_day_time=time.time(),
        max_year=25.0,
        max_year_time=time.time(),
        min_day=15.0,
    )

    sql.dailyHousekeeping()

    row = fetch(sql, "temperature", "max_year")
    assert row["max_year"] == 30.0  # updated because 30 > 25, not reset
