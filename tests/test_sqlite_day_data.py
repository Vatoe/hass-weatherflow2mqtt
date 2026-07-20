"""Tests for updateDayData() (day_data table) and writeDailyLog() (dead code
that inserts into a 'daily_log' table with no CREATE TABLE anywhere in the
codebase - not called from anywhere in weatherflow_mqtt.py either, confirmed
via grep. Kept here to document current safe-failure behavior in case it's
ever wired up by a future change without someone noticing the missing table.
"""
import pytest

from weatherflow2mqtt.const import TABLE_DAY_DATA
from weatherflow2mqtt.sqlite import SQLFunctions


@pytest.fixture
def sql():
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_DAY_DATA)
    return instance


def test_update_day_data_stores_all_fields(sql):
    sensor_data = {
        "air_temperature": 21.5,
        "sealevel_pressure": 1013.2,
        "wind_speed_avg": 3.4,
        "relative_humidity": 55,
        "dewpoint": 12.1,
        "illuminance": 30000,
        "rain_duration_today": 0,
        "rain_rate": 0.0,
        "wind_gust": 5.1,
        "wind_lull": 1.2,
        "lightning_strike_energy": 0,
        "lightning_strike_count_today": 0,
        "uv": 4.5,
        "solar_radiation": 620,
    }

    sql.updateDayData(sensor_data)

    cursor = sql.connection.cursor()
    cursor.execute("SELECT air_temperature, relative_humidity, uv FROM day_data")
    row = cursor.fetchone()
    assert row == (21.5, 55, 4.5)


def test_update_day_data_missing_fields_stored_as_null(sql):
    """.get() is used for every field, so a sparse sensor_data dict
    shouldn't crash - missing values just land as NULL."""
    sql.updateDayData({"air_temperature": 18.0})

    cursor = sql.connection.cursor()
    cursor.execute("SELECT air_temperature, wind_gust FROM day_data")
    row = cursor.fetchone()
    assert row == (18.0, None)


def test_write_daily_log_fails_gracefully_no_table(sql):
    """daily_log has no CREATE TABLE anywhere in the codebase and this
    function is never called (confirmed via grep) - this documents that
    it fails safely (caught, logged, returns None) rather than crashing,
    in case something calls it in the future without noticing the gap."""
    result = sql.writeDailyLog({"air_temperature": 20.0})
    assert result is None
