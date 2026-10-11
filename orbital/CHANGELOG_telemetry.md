# Changelog — orbital telemetry link health

## [telemetry 1.2.0] - 2026-10-11 — bad connections + low/normal launchers

Same `patch_telemetry.py`, now version 1.2.0, plus two launchers. On a fresh file the patcher applies everything; on a file already patched with 1.1.0 it upgrades in place. Both routes give byte-identical results.

### Added — launchers (put them next to hannibal_orbital.py)
- `HANNIBAL_NORMAL.bat` sets `HANNIBAL_NET_PROFILE=normal`.
- `HANNIBAL_LOW_INTERNET.bat` sets `HANNIBAL_NET_PROFILE=low`.
- Each starts `hannibal_orbital.py` (else `hannibal_terminal.py`, else `dist\HANNIBAL.exe` / `HANNIBAL.exe`), shows the active profile in the banner, passes extra switches through, and uses `py -3` or `python`, whichever is installed. The .exe only follows the profile after it is rebuilt with this patch.

| | normal | low |
|---|---|---|
| SatNOGS timeouts (connect / read) | 10 s / 30 s | 20 s / 60 s |
| Retries (wait before each) | 2 (3, 8 s) | 3 (5, 15, 30 s) |
| Observations fetched per satellite | up to 150 (6 pages) | up to 50 (2 pages): less data, busy satellites flagged Truncated |
| Network failures in a row before the rest is skipped | 2 | 1 |
| Auto-rescan in the orbital menu | every 30 min | every 6 h ([L] still rescans on demand) |
| N2YO / Space-Track / NASA requests | unchanged (20 s, 2 retries) | 20 s / 60 s, 3 retries, cached answers reused 4× longer |
| Link fully down, worst case | about 80 s | about 130 s (patient on the first satellite, then skips) |

### Changed — run_telemetry.py
- **Split timeouts** and **retries** on timeouts, dropped connections (including a reply cut off mid-download), 429 and 5xx. A server's `Retry-After` is honoured, up to 30 s. A 404 or other client error fails at once with no retry.
- **Last known value instead of LINK ERROR:** when a satellite can't be fetched, its previous result from `telemetry_report.json` is kept and marked with `*` (e.g. `78% 64/82 [68-86]*`). Rows carry `From Cache`. The `*` never stacks up across failed scans. With nothing cached, it shows LINK ERROR as before.
- **Offline short-cut:** after the profile's limit of network failures in a row, the rest are skipped and filled from the cache instead of each timing out in turn.
- Unchanged: if every satellite fails, the previous report file is left untouched.
- New constants at the top: `LOW_NET`, `CONNECT_TIMEOUT`, `READ_TIMEOUT`, `RETRIES`, `BACKOFF`, `OFFLINE_AFTER` (plus `MAX_PAGES = 2` in the low profile).

### Changed — hannibal_orbital.py
- `SAT_STALE_SECONDS` becomes 6 h in the low profile.
- [L] footer explains the `*` marker.

### Changed — hannibal_net.py
- `Net.request()` applies the low profile when `HANNIBAL_NET_PROFILE=low`; does nothing in normal.

### Changed — the patcher itself
- Backups are now `<file>.pre-telemetry.bak`, not `.bak`. `patch_orbital.py` already keeps `hannibal_net.py.bak` (the pre-security-patch copy); a shared name would have meant a telemetry `--revert` silently undid the security patch. Tested: after patch_orbital → patch_telemetry → telemetry `--revert`, the security patch and its `.bak` are both intact.
- On a file already patched with 1.1.0, the `.pre-telemetry.bak` holds the 1.1.0 version, and 1.1.0's own `.bak` still holds the original.

### Why
Slow, dropping connection in Antwerp: one timeout used to turn a satellite into LINK ERROR and threw away a good earlier reading, a dead link meant waiting through every satellite's timeout, and the orbital menu re-downloaded the whole fleet every 30 minutes.

### Verified
- Fresh apply: 14 of 14 anchors patched, all four files compile, self-test all pass.
- Upgrade 1.1.0 → 1.2.0: byte-identical to a fresh 1.2.0 apply (all four files).
- Re-apply is a no-op; `--revert` restores the originals byte for byte.
- Coexists with patch_orbital (see above).
- Profiles read back correctly in both modes (timeouts, retries, pages, rescan interval).
- Simulated networks (mocked sessions, waits recorded instead of slept):
  1. good link: 7 calls, 0 errors
  2. every first attempt times out: 14 calls, 0 errors, correct statuses
  3. 429 with Retry-After 5: waited 5 s, 0 errors
  4. 404: 7 calls, no retries, all rows from cache
  5. link down, normal: 6 calls, all 7 rows from cache with `*`, old report kept; low: 4 calls, same result
  6. one satellite down: that row from cache, report written, `*` doesn't stack
  7. provider request failing 3× then succeeding: normal gives up (3 attempts), low gets through (4th attempt, 20 s / 60 s timeout)

### Not verified
- Not run on the real Antwerp connection or live SatNOGS from here.
- Launchers were checked as text with Windows line endings, not run on Windows.
- A row from cache shows the old reading; how old is only visible as the report's age in the [L] screen, not per row.


## [telemetry 1.1.0] - 2026-10-11

Delivered as `patch_telemetry.py` (dry run by default, `--apply`, `--revert`, `--selftest`).
Nothing changes on disk until you run it with `--apply`; each touched file is copied to `<name>.bak` first.

### Changed — run_telemetry.py (the maths)
- **Packet health = good / (good + bad).** SatNOGS `failed` means the ground station broke (no audio or waterfall uploaded), so it no longer counts against the satellite. It is reported per row as `Station Failures`.
- **Verdicts need evidence.** Under 8 vetted observations the status is `LOW SAMPLE` (the % is still shown).
  `ONLINE` needs ≥ 75% **and** a 95% Wilson lower bound ≥ 50%. `OFFLINE` needs < 25% **and** an upper bound < 50%. Everything else is `INTERMITTENT`.
  New `STATION FAULT` when every observation failed at the station.
- **Packet Health text** now shows counts and the 95% range: `78% 64/82 [68-86]` (whole percent so it fits the 20-wide column).
- **TLE age.** Rows carry `TLE Age Days` and `TLE Stale` (older than 14 days).
- **Page cap.** If SatNOGS had more pages than `MAX_PAGES` (6 × 25), the row is flagged `Truncated`: its health came from a partial window.
- New helpers: `wilson()`, `health_text()`, `tle_age_days()`; constants `MIN_SAMPLE`, `ONLINE_PCT`, `OFFLINE_PCT`, `CONFIDENT`, `WILSON_Z`, `STALE_TLE_DAYS` at the top of the file.
- `summarize()` now returns `(good, bad, failed, unvetted)`, and `classify()` takes `(good, bad, failed, unvetted)`. Nothing outside run_telemetry.py called either function (checked hannibal_orbital, hannibal_blueglobe, hannibal_telemetry_node, hannibal_feeder).

### Changed — hannibal_orbital.py (display only)
- Fleet table: the new labels are coloured grey instead of uncoloured, and a stale TLE epoch is printed in red. Same in the [L] screen.
- [L] footer now explains the formula, the 95% range, LOW SAMPLE and the red epoch.
- Compatible with today's Earth-export hook (hannibal_sat v0.1.1): different part of the file, either order works. Tested both ways.

### Changed — blueglobe_dashboard.html (display only)
- `LOW SAMPLE` and `STATION FAULT` shown grey.
- An unknown status label now falls back to grey instead of green, so a new label can never look healthy by accident.
- HUD adds ` (STALE)` after a stale TLE epoch.

### Why
The 2026-10 fleet scan called METEOR M-2 OFFLINE on one observation, called LAPAN-A2 100% ONLINE on four, and showed LAPAN-A2's 497-day-old TLE epoch in green. The percentages were arithmetically right; the verdicts claimed more than the counts support. Same principle as the bounded/evidence-gated fixes in the main Hannibal equations.

What the 2026-10 scan becomes (failed counts not visible on screen, so treated as bad, the worst case for the satellite):

| Target | Before | After |
|---|---|---|
| ISS | ONLINE 78.0% (82 rx) | ONLINE 78% 64/82 [68-86] |
| FUNcube-1 | ONLINE 80.0% (5 rx) | LOW SAMPLE 80% 4/5 [38-96] |
| LAPAN-A2 | ONLINE 100.0% (4 rx) | LOW SAMPLE 100% 4/4 [51-100], epoch red |
| JAS-2 (FO-29) | INTERMITTENT 38.5% (13 rx) | INTERMITTENT 38% 5/13 [18-64] |
| OSCAR 7 | OFFLINE 0.0% (4 rx) | LOW SAMPLE 0% 0/4 [0-49] |
| METEOR M-2 | OFFLINE 0.0% (1 rx) | LOW SAMPLE 0% 0/1 [0-79], or STATION FAULT if that pass failed at the station |
| ESTCube-1 | UNVETTED | UNVETTED |

### Verified
- Applied to the reviewed copies of run_telemetry.py, hannibal_orbital.py and blueglobe_dashboard.html: 11 of 11 anchors patched, both Python files compile, and `import hannibal_orbital` succeeds.
- Tested on hannibal_orbital.py with **and** without the Earth-export hook.
- Self-test: 7 of 7 scan cases, 8 of 8 edge cases, TLE-age check (LAPAN-A2 = 497.8 days). All pass.
- End-to-end `scan()` with a mocked SatNOGS session: new fields present in rows, `telemetry_report.json` written through `redact()`, coloured fleet table renders, truncation flag set when pages run past the cap.
- Re-running `--apply` is a no-op (all 11 report "already applied"). `--revert` restores all three files byte-identical.

### Not verified
- Not run against live SatNOGS or Space-Track from here.
- Dashboard change checked as text only; not opened in a browser.
- Thresholds (8 observations, 50% confidence line, 14-day TLE age) are judgement calls. Change them at the top of run_telemetry.py; no other code needs to change.
- AO-7 transmits only in sunlight, so a LOW SAMPLE or OFFLINE result in a 24 h window can mean the passes were in eclipse.
- `.bak` files are a single generation: a second `--apply` after editing keeps the first backup.

### Run it
```
cd <folder with run_telemetry.py>
python patch_telemetry.py            # dry run
python patch_telemetry.py --apply    # writes, then runs the self-test
python patch_telemetry.py --revert   # undo
```
Rebuild the .exe afterwards (build.bat / PyInstaller) for the packaged version to pick it up.
