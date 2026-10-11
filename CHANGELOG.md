# Hannibal changelog

Newest first. Each entry says what changed, why, and what was and was not verified.
Per-module detail lives next to the module (e.g. orbital/CHANGELOG_telemetry.md).

## 2026-10-11 — Orbital Directorate integrated into main (+ FRED, market brain, happiness theorem)
- `orbital/` is now the complete, merged Orbital Directorate: your running Desktop copy + the GEOINT update (TELECOM3) + `hannibal_estimation.py` + the security patch + the Earth-export hook + telemetry 1.2.0. Everything applied cleanly; nothing removed.
- New: `[M]` Macro (FRED, key in the OS credential store), `[R]` Market brain [DEV], `[T]` Happiness theorem [DEV] with a THEOREM card on the brain page. Developer-only behind a PBKDF2 key gate, local-only server, single-use launch code, strict CSP, breach log.
- Soviet-styled NORMAL / LOW INTERNET launchers; Soviet banner and a what's-new section in `orbital/README.md`.
- Fixed: old home coordinates left in `blueglobe_dashboard.html`'s fallback config; stray `.pyc` from PR #1 removed; `.gitignore` for private and runtime files (your theorem profile is never committed).
- `ROADMAP.md`: the complete project roadmap carried over word for word with a status column and stage 11 (macro & market brain). Old roadmap PDFs and earlier release notes collected in `docs/`.
- Tests: brain/FRED/security 34/34, theorem 18/18, telemetry 16/16, masking 8/8, page rendered at desktop and phone width with no errors.
- Full detail: orbital/CHANGELOG.md

## 2026-10-11 — orbital telemetry 1.2.0 (bad connections + launchers)
- `orbital/patch_telemetry.py` 1.2.0: split timeouts, retries with back-off, last known result kept and marked `*` when SatNOGS can't be reached, offline short-cut. Two network profiles via `HANNIBAL_NET_PROFILE`; also covers N2YO / Space-Track / NASA through hannibal_net. Backups now `*.pre-telemetry.bak` so patch_orbital's `hannibal_net.py.bak` is never touched. Upgrades a 1.1.0-patched file in place.
- `orbital/HANNIBAL_NORMAL.bat`, `orbital/HANNIBAL_LOW_INTERNET.bat`: launchers that set the profile.
- Full detail: orbital/CHANGELOG_telemetry.md

## 2026-10-11 — orbital telemetry 1.1.0
- `orbital/patch_telemetry.py`: evidence-gated SatNOGS link health (LOW SAMPLE under 8 observations, 95% Wilson ranges, station failures no longer count against the satellite, stale-TLE flag, page-cap truncation flag). Patches run_telemetry.py, hannibal_orbital.py and blueglobe_dashboard.html; dry run by default, `.bak` backups, `--revert`.
- Full detail: orbital/CHANGELOG_telemetry.md
