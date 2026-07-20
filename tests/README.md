# Tests

Targeted regression tests for the fixes shipped in this fork, not a full test suite for the whole add-on. `weatherflow2mqtt/sqlite.py` only imports the standard library plus its own `const.py`, so these run with nothing beyond `pytest` installed - no MQTT broker, no real database file, no network.

## Running

```
pip install pytest
pytest tests/
```

Also runs automatically on every push via `.github/workflows/test.yml` (GitHub Actions) - check the repo's Actions tab or the commit's status check.

Every test uses an in-memory SQLite database (`:memory:`), created fresh per test via a fixture - nothing touches disk, nothing depends on test order.

## What's covered and why

| File | Covers |
|------|--------|
| `test_sqlite_high_low.py` | `updateHighLow()` - the original High/Low table crash (comparing a sensor value against a `NULL` stored max/min), the per-row isolation fix (one sensor's bad data can't block another sensor's update in the same cycle), and the `math.isfinite()` guard that rejects NaN/Infinity instead of silently writing it to the database. |
| `test_sqlite_write_pressure.py` | `writePressure()` - the same non-finite-value bug pattern, found later while scoping how widespread the issue was elsewhere in the file. |
| `test_sqlite_storage.py` | `create_storage_row()`/`readStorage()`/`writeStorage()` - the rain/lightning running-counter table. |
| `test_sqlite_pressure_lightning.py` | `readPressureTrend()` (incl. the tighter imperial-units threshold) and `writeLightning()`/`readLightningCount()`'s time-window math. |
| `test_sqlite_day_data.py` | `updateDayData()`, plus documents `writeDailyLog()` as confirmed dead code - no `daily_log` table exists anywhere in the codebase, and it's never called. |
| `test_sqlite_lifecycle.py` | `readHighLow()`'s JSON/ISO-timestamp formatting, `initializeHighLow()`'s seed data, `createInitialDataset()`'s full bootstrap, and `upgradeDatabase()`'s schema migration (using a deliberately-reconstructed pre-migration schema, since the current `TABLE_HIGH_LOW` constant already bakes in the columns that migration is supposed to add). |
| `test_sqlite_housekeeping.py` | `dailyHousekeeping()`'s deterministic rollover logic (pressure/lightning cleanup, all-time rollup, yesterday-copy ordering, day reset) plus a year-boundary test using a real 400-day relative time offset - no clock mocking needed, since SQLite's own `strftime('now')` just reads real wall-clock time and a 400-day-old timestamp is guaranteed to cross a calendar year. |

Every file tests the *behavior* the code is supposed to guarantee, not implementation details - seed a row, call the real method, assert on what actually landed in the database afterward.

**Deliberately not covered even within `sqlite.py`:** the month/week boundary branches in `dailyHousekeeping()` (same relative-offset technique as the year case would work, but week boundaries specifically have enough edge-case subtlety near year-end - SQLite's `%W` week-number format resets at Jan 1 regardless of what weekday that falls on - that a naive test risked being flaky for limited incremental value over the year case already covered). And `weatherflow_mqtt.py` (the MQTT/UDP orchestration layer) has no coverage at all - that's async code talking to a real broker and parsing live UDP packets, a meaningfully bigger lift than anything here (real mocking infrastructure needed, not just an in-memory database).

## Confirming these tests are meaningful

Before shipping, each set of tests was run against the **pre-fix** version of `sqlite.py` (checked out from git history) to confirm they actually fail without the fix - not just pass regardless of what the code does. For `test_sqlite_high_low.py`, exactly the 3 tests exercising the None-guard, per-row isolation, and both-max-and-min-change paths failed, reproducing the exact production error that used to spam the logs:

```
'>' not supported between instances of 'float' and 'NoneType'
```

The other tests passed unchanged, since they cover behavior the original code already got right.

## What's deliberately *not* covered

The rest of `sqlite.py` (the daily/weekly/monthly/yearly rollover logic in `dailyHousekeeping()`, storage migration, database versioning) isn't tested here. Most of it only ever interpolates self-generated timestamps or hardcoded constants into SQL - not live, untrusted sensor data - so it doesn't share the specific failure mode these tests target. See `docs/TODO_COMPLETED.md` (household config repo) SYS-20 for the full audit of what was checked and why the rest was left alone.
