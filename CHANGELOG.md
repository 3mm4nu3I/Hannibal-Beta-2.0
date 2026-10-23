# Hannibal changelog

Newest first. Each entry says what changed, why, and what was and was not verified.
Per-module detail lives next to the module (e.g. orbital/CHANGELOG_telemetry.md).

## 2026-10-23 (later) — Moonbounce: choose dish or Yagi, band-aware noise
- `[E]` now asks for the antenna: a dish (prime-focus, offset or mesh, and its diameter) or a Yagi array (gain of one Yagi and how many), on any band. Defaults: Yagi arrays on 6 m / 2 m / 70 cm, a 3 m dish from 23 cm up.
- System noise is worked out per band and antenna (receiver + galactic sky + the Moon's own glow + ground) instead of one fixed 100 K. A 4-Yagi 2 m station had looked 4.3 dB better than it is.
- The +51.8 dB processing-gain line is labelled as a theoretical ceiling that is not in the SNR.
- `RUN_EME.bat` keeps working unchanged (same answers, same result). 14 EME tests pass; live runs over Antwerp for 23 cm and 2 m.
- Full detail: orbital/CHANGELOG.md

## 2026-10-23 — Sync: the laptop's work merged into main
- `feature/eme-moonbounce` (16-17 Oct: home-location fix, `[E]` Moonbounce, N2YO altitude guard) merged into main. It matches the laptop's running copy exactly, so main now holds everything: the laptop's work plus `[W]`, `[D]` and `[Z]`.
- One conflict (orbital/CHANGELOG.md), both sides kept. All tests pass; `[Z]`, `[W]`, `[E]` checked through the merged menu. Backup of main: branch `backup/main-2026-10-23-pre-sync`.
- Full detail: orbital/CHANGELOG.md

## 2026-10-23 — Receive-only and the law
- `orbital/README.md` has a new section on Belgian rules for receive-only listening, from the Orbital Directorate's 22 Oct memo: no licence to listen, licences only to transmit, ONL listener number voluntary, and BIPT's limit on what may be listened to (open frequencies only; no military traffic). Documentation only.
- Full detail: orbital/CHANGELOG.md

## 2026-10-22 (evening) — Zombie check (`[Z]`)
- New `[Z] Zombie check` (`orbital/hannibal_zombie.py`, `--zombie`): for a list of satellites, which ones still transmit something an amateur station can hear, from the SatNOGS DB (transmitters on record) and Network (vetted observations in the last 30 days). Default list: the 148 military objects in the 17 Oct Antwerp export. Receive-only, no key.
- Result, live 22 Oct 2026: **2 of 148 heard** (COSMOS 2488 on UHF FM; ERS 15, launched 1966, on a 136.439 MHz CW carrier), **0 with an uplink on record**. 142 have no transmitter known to the amateur network.
- ERS 15 added to the fleet watch list (`orbital/norad_targets.json`), so every fleet telemetry scan now checks it. First scan: UNVETTED (one observation awaiting vetting); 30 days: 2 good of 7 vetted, LOW SAMPLE.
- Tests: `orbital/test_hannibal_zombie.py` passes offline; every other orbital test and the root fixtures still pass.
- Full detail and limits: orbital/CHANGELOG.md

## 2026-10-22 — Where it won't be (`[W]`), Kessler sensitivity, and the day's merges
- Backups before this work: branch `backup/main-2026-10-22-pre-neo` (main at 56cb371) and a full git bundle of every branch, sent separately. Earlier today: branch `backup/bat-crlf-2026-10-22` (main at 8fe8a4a) before the line-ending fix.
- New `[W] Where it won't be` (`orbital/hannibal_neo.py`, `--neo DES`): Earth-impact exclusion for any asteroid or comet from NASA/JPL close-approach data. Each pass is checked against Earth plus 100 km of atmosphere at the nearest edge of JPL's 3-sigma window. The overall verdict always defers to JPL Sentry, because a pass that clears Earth can still lead through a keyhole to a later impact (Bennu is the worked example). Receive-only, no key.
- `[D] Debris cascade` now says how robust each shell's status is: the factor by which the two roughest assumptions (fragments per collision, drag lifetime) would have to be off before the shell crosses the line. Long-lived, low-index shells are labelled "quiet (slow to clear)" instead of "self-cleaning".
- Merged today: #6 Kessler cascade watch (`[D]`, `--kessler`), #7 the three orbital `.bat` launchers stored with LF like every other `.bat` (checkout still gives CRLF; working trees are no longer shown as modified).
- Tests: `orbital/test_hannibal_neo.py` and `orbital/test_hannibal_kessler.py` pass offline; the existing subsea/spatial and evidence-confidence fixtures still pass. `[W]` and `[D]` driven through `run_menu`; live runs on Apophis, Bennu, Eros, 2024 YR4 and an invalid name.
- Full detail: orbital/CHANGELOG.md

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
