"""Tests for the storage table (rain/lightning running counters)."""
import pytest

from weatherflow2mqtt.const import STORAGE_ID, TABLE_STORAGE
from weatherflow2mqtt.sqlite import SQLFunctions


@pytest.fixture
def sql():
    instance = SQLFunctions(unit_system="metric", debug=False)
    instance.create_connection(":memory:")
    instance.create_table(TABLE_STORAGE)
    return instance


def test_create_and_read_storage_row(sql):
    row = (STORAGE_ID, 5.0, 3.0, 1700000000.0, 10, 20, 2, 1, 1700000100.0, 500, 1000)
    sql.create_storage_row(row)

    data = sql.readStorage()

    assert data["rain_today"] == 5.0
    assert data["rain_yesterday"] == 3.0
    assert data["lightning_count"] == 2
    assert data["lightning_count_today"] == 1


def test_write_storage_updates_existing_row(sql):
    sql.create_storage_row(
        (STORAGE_ID, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    )

    sql.writeStorage(
        {
            "rain_today": 12.5,
            "rain_yesterday": 8.0,
            "rain_start": 1700000000.0,
            "rain_duration_today": 45,
            "rain_duration_yesterday": 30,
            "lightning_count": 7,
            "lightning_count_today": 3,
            "last_lightning_time": 1700000200.0,
            "last_lightning_distance": 12,
            "last_lightning_energy": 900,
        }
    )

    data = sql.readStorage()
    assert data["rain_today"] == 12.5
    assert data["lightning_count"] == 7
    assert data["last_lightning_distance"] == 12
