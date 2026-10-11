# Hannibal changelog

Newest first. Each entry says what changed, why, and what was and was not verified.
Per-module detail lives next to the module (e.g. orbital/CHANGELOG_telemetry.md).

## 2026-10-11 — orbital telemetry 1.1.0
- `orbital/patch_telemetry.py`: evidence-gated SatNOGS link health (LOW SAMPLE under 8 observations, 95% Wilson ranges, station failures no longer count against the satellite, stale-TLE flag, page-cap truncation flag). Patches run_telemetry.py, hannibal_orbital.py and blueglobe_dashboard.html; dry run by default, `.bak` backups, `--revert`.
- Full detail: orbital/CHANGELOG_telemetry.md
