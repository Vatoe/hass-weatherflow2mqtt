# Tests

Targeted regression tests for the fixes shipped in this fork, not a full test suite for the whole add-on. `weatherflow2mqtt/sqlite.py` only imports the standard library plus its own `const.py`, so these run with nothing beyond `pytest` installed - no MQTT broker, no real database file, no network.

## Running

```
pip install pytest
pytest tests/
```

Every test uses an in-memory SQLite database (`:memory:`), created fresh per test via a fixture - nothing touches disk, nothing depends on test order.

## What's covered and why

| File | Covers |
|------|--------|
| `test_sqlite_high_low.py` | `updateHighLow()` - the original High/Low table crash (comparing a sensor value against a `NULL` stored max/min), the per-row isolation fix (one sensor's bad data can't block another sensor's update in the same cycle), and the `math.isfinite()` guard that rejects NaN/Infinity instead of silently writing it to the database. |
| `test_sqlite_write_pressure.py` | `writePressure()` - the same non-finite-value bug pattern, found later while scoping how widespread the issue was elsewhere in the file. |

Both files test the *behavior* those fixes are supposed to guarantee, not implementation details - they seed a `high_low`/`pressure` row, call the real method, and assert on what actually landed in the database afterward.

## Confirming these tests are meaningful

Before shipping, each set of tests was run against the **pre-fix** version of `sqlite.py` (checked out from git history) to confirm they actually fail without the fix - not just pass regardless of what the code does. For `test_sqlite_high_low.py`, exactly the 3 tests exercising the None-guard, per-row isolation, and both-max-and-min-change paths failed, reproducing the exact production error that used to spam the logs:

```
'>' not supported between instances of 'float' and 'NoneType'
```

The other tests passed unchanged, since they cover behavior the original code already got right.

## What's deliberately *not* covered

The rest of `sqlite.py` (the daily/weekly/monthly/yearly rollover logic in `dailyHousekeeping()`, storage migration, database versioning) isn't tested here. Most of it only ever interpolates self-generated timestamps or hardcoded constants into SQL - not live, untrusted sensor data - so it doesn't share the specific failure mode these tests target. See `docs/TODO_COMPLETED.md` (household config repo) SYS-20 for the full audit of what was checked and why the rest was left alone.
