# Changelog — orbital telemetry link health

## [telemetry 1.2.0] - 2026-10-11 — bad connections

Same `patch_telemetry.py`, now version 1.2.0. On a fresh file it applies everything; on a file already patched with 1.1.0 it upgrades in place. Both routes give byte-identical results. The `.bak` from the first run (the original) is kept, so `--revert` still goes back to the unpatched files.

### Changed — run_telemetry.py
- **Split timeouts:** 10 s to connect, 30 s between chunks of data (was 15 s for everything). A slow link no longer cuts the SatNOGS reply off half-way.
- **Retries:** a timeout, dropped connection (including a reply cut off mid-download), 429 or 5xx is retried twice, after 3 s and then 8 s. A server's `Retry-After` is honoured, up to 30 s. A 404 or other client error fails at once with no retry.
- **Last known value instead of LINK ERROR:** when a satellite can't be fetched, its previous result from `telemetry_report.json` is kept and marked with `*` (e.g. `78% 64/82 [68-86]*`). Rows carry `From Cache`. The `*` never stacks up across failed scans. With nothing cached, it shows LINK ERROR as before.
- **Offline short-cut:** after 2 satellites in a row fail at the network level, the rest are skipped and filled from the cache instead of each timing out in turn. A dead link now costs about 80 s instead of several minutes.
- Unchanged: if every satellite fails, the previous report file is left untouched (`write_report` returns False), exactly as before.
- New constants at the top: `CONNECT_TIMEOUT`, `READ_TIMEOUT`, `RETRIES`, `BACKOFF`, `OFFLINE_AFTER`.

### Changed — hannibal_orbital.py
- [L] footer explains the `*` marker.

### Why
Slow, dropping connection in Antwerp: one timeout used to turn a satellite into LINK ERROR and threw away a perfectly good earlier reading, and a dead link meant waiting through every satellite's timeout.

### Verified
- Fresh apply: 12 of 12 anchors patched, self-test all pass.
- Upgrade 1.1.0 → 1.2.0: 4 anchors upgraded, 1 new, the rest already applied; result byte-identical to a fresh 1.2.0 apply.
- Re-apply is a no-op; `--revert` restores the originals byte for byte.
- Simulated networks (mocked SatNOGS session, sleeps recorded instead of waited):
  1. good link: 7 calls, 0 errors
  2. every first attempt times out: 14 calls, 0 errors, correct statuses
  3. 429 with Retry-After 5: waited 5 s, 0 errors
  4. 404: 7 calls, no retries, all rows from cache
  5. link down: 6 calls (2 satellites × 3 attempts), rest skipped, all 7 rows from cache with `*`, old report file kept
  6. one satellite down: that row from cache, report written, `*` doesn't stack on a second failure

### Not verified
- Not run on the real Antwerp connection or live SatNOGS from here.
- Space-Track has its own cache and limits in hannibal_spacetrack.py and was not changed.
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
