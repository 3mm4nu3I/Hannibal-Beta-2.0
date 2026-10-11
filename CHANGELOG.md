# Hannibal changelog

Newest first. Each entry says what changed, why, and what was and was not verified.
Per-module detail lives next to the module (e.g. orbital/CHANGELOG_telemetry.md).

## 2026-10-11 — orbital telemetry 1.2.0 (bad connections)
- `orbital/patch_telemetry.py` 1.2.0: split timeouts (10 s connect / 30 s read), 2 retries with back-off (Retry-After honoured), last known result kept and marked `*` when SatNOGS can't be reached, rest of the scan skipped after 2 network failures in a row. Upgrades a 1.1.0-patched file in place.
- Full detail: orbital/CHANGELOG_telemetry.md

## 2026-10-11 — orbital telemetry 1.1.0
- `orbital/patch_telemetry.py`: evidence-gated SatNOGS link health (LOW SAMPLE under 8 observations, 95% Wilson ranges, station failures no longer count against the satellite, stale-TLE flag, page-cap truncation flag). Patches run_telemetry.py, hannibal_orbital.py and blueglobe_dashboard.html; dry run by default, `.bak` backups, `--revert`.
- Full detail: orbital/CHANGELOG_telemetry.md
