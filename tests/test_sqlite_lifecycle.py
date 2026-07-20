"""Tests for high_low read/seed, and full database lifecycle
(createInitialDataset, upgradeDatabase)."""
import datetime

import pytest

from weatherflow2mqtt.const import (
    DATABASE_VERSION,
    STORAGE_ID,
    TABLE_HIGH_LOW,
)
from weatherflow2mqtt.sqlite import SQLFunctions


@pytest.fixture
def sql():
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_HIGH_LOW)
    return instance


def test_read_high_low_converts_timestamps_to_iso(sql):
    ts = 1700000000.0  # 2023-11-14T22:13:20+00:00
    cursor = sql.connection.cursor()
    cursor.execute(
        "INSERT INTO high_low(sensorid, max_day, max_day_time, min_day) "
        "VALUES('temperature', 25.0, ?, 10.0)",
        (ts,),
    )
    sql.connection.commit()

    data = sql.readHighLow()

    assert data["temperature"]["max_day"] == 25.0
    expected_iso = (
        datetime.datetime.utcfromtimestamp(round(ts))
        .replace(tzinfo=datetime.timezone.utc)
        .isoformat()
    )
    assert data["temperature"]["max_day_time"] == expected_iso
    assert data["temperature"]["min_day"] == 10.0


def test_read_high_low_null_timestamp_stays_none(sql):
    cursor = sql.connection.cursor()
    cursor.execute(
        "INSERT INTO high_low(sensorid, max_day) VALUES('humidity', 80.0)"
    )
    sql.connection.commit()

    data = sql.readHighLow()

    assert data["humidity"]["max_day_time"] is None


def test_initialize_high_low_seeds_expected_sensors(sql):
    sql.initializeHighLow()

    cursor = sql.connection.cursor()
    cursor.execute("SELECT sensorid, max_day, min_day FROM high_low")
    rows = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

    assert len(rows) == 14
    # Temperature/humidity/pressure/dewpoint use sentinel extremes so the
    # first real reading always wins the comparison in updateHighLow().
    assert rows["air_temperature"] == (-9999, 9999)
    assert rows["relative_humidity"] == (-9999, 9999)
    # Counters/rates start at zero rather than a sentinel extreme.
    assert rows["illuminance"] == (0, 0)
    assert rows["uv"] == (0, 0)


def test_create_initial_dataset_full_bootstrap(tmp_path, monkeypatch):
    import weatherflow2mqtt.sqlite as sqlite_module

    # Point the legacy-migration file check at a guaranteed-nonexistent
    # path so this test doesn't depend on the host filesystem.
    monkeypatch.setattr(sqlite_module, "STORAGE_FILE", str(tmp_path / "nope.json"))

    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")

    instance.createInitialDataset()

    cursor = instance.connection.cursor()
    cursor.execute("SELECT id FROM storage")
    assert cursor.fetchone()[0] == STORAGE_ID

    cursor.execute("SELECT COUNT(*) FROM high_low")
    assert cursor.fetchone()[0] == 14

    cursor.execute("PRAGMA main.user_version;")
    assert cursor.fetchone()[0] == DATABASE_VERSION


# TABLE_HIGH_LOW (the current constant) already bakes in the yday columns
# for fresh installs. upgradeDatabase()'s ALTER TABLE branch exists for
# real pre-existing databases on disk that predate that - so testing it
# needs its own genuinely-old schema, not the fixture's current one.
LEGACY_TABLE_HIGH_LOW_V1 = """
    CREATE TABLE IF NOT EXISTS high_low (
        sensorid TEXT PRIMARY KEY,
        latest REAL,
        max_day REAL,
        max_day_time REAL,
        min_day REAL,
        min_day_time REAL,
        max_week REAL,
        max_week_time REAL,
        min_week REAL,
        min_week_time REAL,
        max_month REAL,
        max_month_time REAL,
        min_month REAL,
        min_month_time REAL,
        max_year REAL,
        max_year_time REAL,
        min_year REAL,
        min_year_time REAL,
        max_all REAL,
        max_all_time REAL,
        min_all REAL,
        min_all_time REAL
    );
"""


def test_upgrade_database_adds_yday_columns_from_v1():
    """A database on the pre-yday-columns schema, left at PRAGMA
    user_version 1, should get the 4 missing columns added without
    losing existing data."""
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(LEGACY_TABLE_HIGH_LOW_V1)
    cursor = instance.connection.cursor()
    cursor.execute(
        "INSERT INTO high_low(sensorid, max_day) VALUES('temperature', 22.0)"
    )
    cursor.execute("PRAGMA main.user_version = 1;")
    instance.connection.commit()

    instance.upgradeDatabase()

    cursor.execute("PRAGMA table_info(high_low)")
    columns = {row[1] for row in cursor.fetchall()}
    assert {"max_yday", "max_yday_time", "min_yday", "min_yday_time"} <= columns

    cursor.execute("SELECT max_day FROM high_low WHERE sensorid = 'temperature'")
    assert cursor.fetchone()[0] == 22.0


def test_upgrade_database_noop_when_already_current(sql, caplog):
    """Already at DATABASE_VERSION - upgradeDatabase() must genuinely
    no-op (neither the v1-init nor the ALTER branch should even attempt
    to run), not silently swallow a duplicate-column error. The function
    has a blanket except-and-log with no re-raise, so a bug here wouldn't
    raise an exception at all - checking for the absence of a logged
    error is the only way to actually catch that, versus "did it raise"
    which is true regardless of whether the no-op path or a caught-error
    path is what actually happened."""
    cursor = sql.connection.cursor()
    cursor.execute(f"PRAGMA main.user_version = {DATABASE_VERSION};")
    sql.connection.commit()

    sql.upgradeDatabase()

    cursor.execute("PRAGMA main.user_version;")
    assert cursor.fetchone()[0] == DATABASE_VERSION
    assert not any(r.levelname == "ERROR" for r in caplog.records)
