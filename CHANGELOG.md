# Change Log

All notable changes to this project will be documented in this file. 

## [3.2.4] - 2026-07-20

### Changes (fork - github.com/Vatoe/hass-weatherflow2mqtt)

- Bumped `pytest` 4.4.1 -> 9.0.3 in test tooling (fixes CVE-2025-71176, insecure tmpdir handling)
- Added CI (GitHub Actions) to run the test suite automatically on every push
- Extended test coverage to the rest of `sqlite.py` - storage/pressure/lightning/day_data tables, database lifecycle (create/upgrade/seed), and `dailyHousekeeping()`'s rollover logic (34 additional tests)

## [3.2.3] - 2026-07-20

### Changes (fork)

- Fixed `writePressure()` interpolating live sensor values directly into SQL text (same bug class as the High/Low table crash below) - parameterized query + non-finite (NaN/Infinity) guard added

## [3.2.2-fix4] - 2026-07-20

### Changes (fork)

- Bumped `pyweatherflowudp` 1.4.2 -> 1.5.2 (the UDP-parsing library, still independently maintained even though this add-on isn't upstream) - validated by running every `calc.py` physics function against known-correct reference values before shipping

## [3.2.2-fix3] - 2026-07-20

### Changes (fork)

- Bumped stale dependencies: `paho-mqtt` 1.6.1 -> 2.1.0, `aiohttp` 3.8.4 -> 3.14.1, `PyYAML`, `pytz`
- Parameterized `updateHighLow()`'s SQL instead of interpolating live sensor values into SQL text, with a non-finite (NaN/Infinity) guard
- Added the first test suite (`tests/`)

## [3.2.2-fix2] - 2026-07-20

### Changes (fork)

- Isolated per-sensor failures in `updateHighLow()` - one sensor's bad data no longer aborts every other sensor's high/low and "latest" update in the same cycle, only its own

## [3.2.2-fix1] - 2026-07-20

### Changes (fork)

- Forked from `briis/hass-weatherflow2mqtt` (archived/unmaintained since 2024-12-29) after the upstream "Could not write to High and Low Table" NoneType crash was confirmed as a known, permanently-unfixed bug
- Fixed the crash at its root: `updateHighLow()` compared a sensor value against a `NULL` stored max/min without guarding against it, throwing a `TypeError` that silently aborted every sensor's update that cycle, not just the affected one - self-healing, no manual database changes needed
- Bumped the Dockerfile base image `python:3.11-slim-buster` -> `slim-bookworm` (buster's Debian repos are no longer served, was blocking builds entirely)

## [3.2.2] - 2023-10-08

### BREAKING Announcement

As there is now a `Home Assistant Core` integration for WeatherFlow which uses the UDP API, I had to make a [new Integration](https://github.com/briis/weatherflow_forecast) that uses the REST API, with a different name (WeatherFlow Forecast). The new integration is up-to-date with the latest specs for how to create a Weather Forecast, and also gives the option to only add the Forecast, and no additional sensors. 

There is no *Weather Entity* in Home Assistant for MQTT, so after attributes are deprecated in Home Assistant 2024.3, there is no option to add the Forecast to Home Assistant.
As a consequence of that, I have decided to remove the ability for this Add-On to add Forecast data to MQTT and Home Assistant. This Add-On will still be maintained, but just without the option of a Forecast - meaning it will be 100% local.
If you want the forecast in combination with this Add-On, install the new integration mentioned above, just leave the *Add sensors* box unchecked.

There is not an exact date for when this will happen, but it will be before end of February 2024.

### Changes

- Added Slovenian language file. This was unfortunately placed in a wrong directory and as such it was not read by the integration. Fixing issue #236
- Fixed issue #244 with deprecated forecast values. Thank you @mjmeli
- Corrected visibility imperial unit from nautical mile (nmi) to mile (mi)

## [3.2.1] - 2023-08-31

### Changes

- Some stations do not get the Sea Level Pressure and/or the UV value in the Hourly Forecast. It is not clear why this happens, but the issue is with WeatherFlow. The change implemented here, ensures that the system does not break because of that. If not present a 0 value is returned.
  This fixes Issue #234, #238 and maybe also #239

## [3.2.0] - 2023-08-29

### Changes

- Fixed wrong type string in the `rain_type` function, so that it should now also get a string for Heavy Rain. Thanks to @GlennGoddard for spotting this. Closing #205
- Changing units using ^ to conform with HA standards
- Adding new device classes to selected sensors. (Wind Speed, Distance, Irradiation, Precipiation etc.)
- Closing #198 and #215, by trying to ensure that correct timezone and unit system is always set
- Added swedish translation. Thank you to @Bo1jo
- Bumped docker image to `python:3.11-slim-buster` and @pcfens optimized the `Dockerfile`` to create a faster and smaller image.
- Bumped all dependency modules to latest available version
- Thanks @quentinmit the following improvements have been made, that makes it easier to run the program without Docker in a more traditional `setuptools` way.
    - Translations are installed and loaded as package data
    - The no-longer-supported asyncio PyPI package is removed from requirements.txt
    - Pint 0.20 and 0.21 are supported (also requires the pyweatherflowudp patch I sent separately)
- @prigorus  added the Slovenian translation

