"""Tests for SQLFunctions.writePressure() - the SYS-20 fix (2026-07-20):
the live pressure reading was interpolated directly into SQL text via
f-string, the same bug class SYS-19 fixed for the high_low table. Now
parameterized, with the same non-finite guard.
"""
import math

import pytest

from weatherflow2mqtt.const import TABLE_PRESSURE
from weatherflow2mqtt.sqlite import SQLFunctions


@pytest.fixture
def sql():
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_PRESSURE)
    return instance


def all_rows(sql):
    cursor = sql.connection.cursor()
    cursor.execute("SELECT timestamp, pressure FROM pressure")
    return cursor.fetchall()


def test_writes_a_normal_value(sql):
    result = sql.writePressure(1013.25)

    assert result is True
    rows = all_rows(sql)
    assert len(rows) == 1
    assert rows[0][1] == 1013.25


def test_writes_negative_and_decimal_values_correctly(sql):
    """Regression check for the parameterization itself - a value that
    would previously round-trip fine via f-string too, just confirming
    the switch to '?' placeholders didn't change normal behavior."""
    sql.writePressure(-12.345)

    rows = all_rows(sql)
    assert rows[0][1] == -12.345


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_value_rejected_not_stored(sql, bad_value):
    result = sql.writePressure(bad_value)

    assert result is False
    assert all_rows(sql) == []


def test_multiple_writes_accumulate(sql):
    """Sanity check the table isn't accidentally keyed/deduped in a way
    that would silently drop consecutive real readings."""
    sql.writePressure(1010.0)
    sql.writePressure(1011.0)
    sql.writePressure(1012.0)

    rows = all_rows(sql)
    assert len(rows) == 3
    assert sorted(r[1] for r in rows) == [1010.0, 1011.0, 1012.0]
