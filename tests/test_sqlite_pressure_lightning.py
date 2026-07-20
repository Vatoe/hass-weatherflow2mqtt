"""Tests for pressure trend calculation and lightning strike tracking."""
import time

import pytest

from weatherflow2mqtt.const import (
    PRESSURE_TREND_TIMER,
    TABLE_LIGHTNING,
    TABLE_PRESSURE,
    UNITS_IMPERIAL,
)
from weatherflow2mqtt.sqlite import SQLFunctions

TRANSLATIONS = {"trend": {"steady": "Steady", "falling": "Falling", "rising": "Rising"}}


@pytest.fixture
def sql():
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_PRESSURE)
    instance.create_table(TABLE_LIGHTNING)
    return instance


def seed_old_pressure(sql, pressure, seconds_old=PRESSURE_TREND_TIMER + 60):
    """Insert a pressure reading old enough for readPressureTrend to use as
    its comparison baseline (must be older than PRESSURE_TREND_TIMER)."""
    cursor = sql.connection.cursor()
    cursor.execute(
        "INSERT INTO pressure(timestamp, pressure) VALUES(?, ?)",
        (time.time() - seconds_old, pressure),
    )
    sql.connection.commit()


def test_new_pressure_none_returns_steady_immediately(sql):
    trend, delta = sql.readPressureTrend(None, TRANSLATIONS)
    assert trend == "Steady"
    assert delta == 0


def test_no_baseline_data_defaults_to_steady(sql):
    """No old-enough row exists - old_pressure defaults to new_pressure, delta 0."""
    trend, delta = sql.readPressureTrend(1013.0, TRANSLATIONS)
    assert trend == "Steady"
    assert delta == 0


def test_steady_trend_within_threshold(sql):
    seed_old_pressure(sql, 1013.0)
    trend, delta = sql.readPressureTrend(1013.5, TRANSLATIONS)
    assert trend == "Steady"


def test_falling_trend(sql):
    seed_old_pressure(sql, 1013.0)
    trend, delta = sql.readPressureTrend(1010.0, TRANSLATIONS)
    assert trend == "Falling"
    assert delta == -3.0


def test_rising_trend(sql):
    seed_old_pressure(sql, 1013.0)
    trend, delta = sql.readPressureTrend(1016.0, TRANSLATIONS)
    assert trend == "Rising"
    assert delta == 3.0


def test_imperial_units_use_tighter_threshold(sql):
    """1 hPa of drift is 'steady' in metric but 'falling' in imperial
    (min/max threshold is +-0.0295 instead of +-1)."""
    instance = SQLFunctions(unit_system=UNITS_IMPERIAL, debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_PRESSURE)
    seed_old_pressure(instance, 1013.0)

    trend, _ = instance.readPressureTrend(1012.0, TRANSLATIONS)
    assert trend == "Falling"


def test_lightning_count_within_window(sql):
    sql.writeLightning()
    sql.writeLightning()

    count = sql.readLightningCount(hours=1)
    assert count == 2


def test_lightning_count_excludes_old_strikes(sql):
    cursor = sql.connection.cursor()
    cursor.execute(
        "INSERT INTO lightning(timestamp) VALUES(?)", (time.time() - 7200,)
    )  # 2 hours ago
    sql.connection.commit()
    sql.writeLightning()  # just now

    assert sql.readLightningCount(hours=1) == 1
    assert sql.readLightningCount(hours=3) == 2
