# Orbital Directorate changelog

Newest first. What changed, why, what was verified, and what was not.
Telemetry 1.1.0 / 1.2.0 detail: [CHANGELOG_telemetry.md](CHANGELOG_telemetry.md).

## [2026-10-22, evening] Zombie check (`[Z]`)

### Why
The 17 Oct satellite detail export lists 148 military objects above Antwerp (an earlier run gave ~135). Those are N2YO positions computed from orbital elements: a satellite that died in 1966 and one that works today look identical in that list. `[Z]` answers the other question, whether anything on them still transmits, with measured evidence instead of a guess.

### Added
- **`hannibal_zombie.py` + `[Z] Zombie check`** (also `python hannibal_orbital.py --zombie` or `python hannibal_zombie.py [--ids ... | --file ... | --above] [--days 30] [--all] [--json out.json]`). Receive-only, no key, every call through `hannibal_net`.
  - Two full-list pulls from the SatNOGS DB (satellites and transmitters, cached 24 h), then SatNOGS Network vetted `good` and `bad` observations, only for objects that have a transmitter on record (cached 1 h, window start rounded to the hour so the cache can hit).
  - Tiers per object: `HEARD` (a vetted good observation in the window), `LISTED, NOT HEARD` (active transmitter on record, nothing heard), `NO ACTIVE TX`, `NOT IN SATNOGS`, and `NOT CHECKED` when the network could not be asked. Any `NOT CHECKED` turns the verdict into a lower bound ("at least") and the exit code into 2; a DB outage is an error, never a silent zero.
  - `UPLINK` column: whether any transmitter on record has an uplink (type Transceiver or Transponder). A relay needs one.
  - Filters are applied again locally (status, object, window), so a server that ignored a filter could not inflate a count. A full page (25) shows as `25+`.
- `zombie_targets_2026-10-17.json`: the 148 NORAD ids and names from section A of the export, in its elevation order (the default target list; no positions, they go stale in minutes). `--above` uses what N2YO lists overhead at run time instead.
- `test_hannibal_zombie.py`: offline tests on trimmed real SatNOGS records and a fake network (tiers, window and foreign rows, page cap, unchecked, DB outage, paginated DB form).
- `hannibal_net.py`: `db.satnogs.org` gets its own limit (1 s spacing). `hannibal_terminal.spec`: `hannibal_zombie` and the target list are bundled into the .exe.
- **ERS 15 (2412) on the fleet watch list** (`norad_targets.json`), so `[1] Fleet telemetry`, `[L]` and `--scan` check it every run. First scan, 24 h window: `UNVETTED` (one observation from that morning still awaiting vetting). Over 30 days: 2 good, 5 bad, 15 unvetted, 5 station failures, i.e. `LOW SAMPLE`, 29% (95% range 8-64%). Expect `NO PASSES` or `UNVETTED` on most 24 h scans: it is only heard now and then. `python hannibal_zombie.py --ids 2412` gives the 30-day view.

### Verified
- Live, 22 Oct 2026 ~18:40 UTC, 30-day window, all 148 targets (12 s cold, 0.1 s cached): **HEARD 2 of 148, with an uplink on record 0.**
  - COSMOS 2488 (39483, launched 2013): 9 good, 0 bad, last 21 Oct 12:45 UTC, UHF FM 388.687 MHz.
  - ERS 15 (2412, launched 1966): 2 good, 5 bad, last 26 Sep 12:40 UTC, CW carrier 136.439 MHz. The one true 1960s survivor on the list, and it is a carrier, not a transponder.
  - LISTED, NOT HEARD: USA 184, YAOGAN 10, YAOGAN 12. NO ACTIVE TX: USA 198 (SDS-3 F-5). NOT IN SATNOGS: 142.
- The same numbers as a hand check with plain HTTP requests against both APIs. All orbital tests pass; the subsea/spatial and evidence-confidence fixtures still pass; `[Z]` driven through `run_menu`; menu is `1 2 3 4 H N 5 6 7 8 9 W Z D G F K I M R T S A Q`.

### Not done / limits
- SatNOGS only knows transmitters amateurs have found and logged. `NOT IN SATNOGS` means no amateur-known transmitter, not proof the satellite is dead; military links on bands amateurs don't monitor (or encrypted) never show up here. For the question "is there anything an amateur station can use", that distinction does not change the answer.
- `LISTED, NOT HEARD` can also mean no volunteer station scheduled that pass in the window.
- `HEARD` is evidence of a working transmitter, not of a link anyone can command.
- Not built on Windows here: the `.exe` needs `build.bat`. Noticed while editing the spec: `hannibal_neo` and `hannibal_kessler` are not in its hidden imports, so `[W]` and `[D]` may be missing from a built `.exe` (they work from source). Left as it was.

## [2026-10-22, later] Where it won't be (`[W]`) and Kessler sensitivity

Backups first: branch `backup/main-2026-10-22-pre-neo` (main at 56cb371) and a full git bundle.

### Added
- **`hannibal_neo.py` + `[W] Where it won't be`** (also `python hannibal_orbital.py --neo 99942` or `python hannibal_neo.py "2024 YR4"`): Earth-impact exclusion for any asteroid or comet. Three NASA/JPL calls through `hannibal_net` (close approaches to 2200 within 0.05 au, Sentry, Small-Body Database), cached 6 h, no key.
  - Each pass: nominal distance, JPL's 3-sigma nearest and farthest distance, window width, clearance above the atmosphere (equatorial radius + 100 km) at the nearest edge, whether it passes inside GEO. `EXCLUDED` when the nearest edge stays above the atmosphere. Rows whose window is wider than the distance are marked `~rough`.
  - Overall verdict defers to Sentry. Listed -> `NOT EXCLUDED` with JPL's impact count, years and cumulative probability, even when every pass clears Earth (keyhole case). Removed or never listed and every pass clear -> `EXCLUDED`. Sentry unreachable or close-approach data missing -> `NO DATA`, never an all-clear.
  - Rows for any other object than the one asked for are refused. An unknown name gets "JPL does not recognise", not "unavailable".
- **Kessler sensitivity** in `[D]`: `x cross` column = how many times larger k (fragments per collision) x tau (drag lifetime) would have to be for the shell to reach index 1. Because the index is proportional to k x tau this is exactly 1 / index. The summary lists shells within 2x of the line.
- `test_hannibal_neo.py` (offline, trimmed real JPL payloads and a fake network); `test_hannibal_kessler.py` extended.

### Changed
- Kessler band labels: a low-index shell with a drag lifetime over 50 years is `quiet (slow to clear)`, not `self-cleaning` (650-750 km and above 1,750 km were mislabelled).

### Verified
- Live, 22 Oct 2026: Apophis EXCLUDED (2029 pass 38,011 km, window 6.6 km, 31,530 km above the atmosphere; Sentry removed 2021-02-21). Bennu NOT EXCLUDED (every pass to 2200 clears Earth, 2135 at 204,041 km; Sentry: 157 impacts 2178-2290, about 1 in 1,749). Eros EXCLUDED (no pass within 0.05 au, never listed). 2024 YR4 EXCLUDED (Sentry removed 2026-03-05; 2032-Dec-22 at 278,333 km). `zzzz9` refused as unrecognised.
- Kessler on the 22 Oct catalog: the 450-500 km Starlink shell would need 16.5x worse assumptions to cross; 750-950 km need 6-9x; 950-1,000 km and 1,200-1,250 km are within 1.3x; 1,150-1,200 km and 1,400-1,600 km are over.
- All orbital tests pass; `hannibal_orbital.py` compiles; `[W]` and `[D]` driven through `run_menu`; repo fixtures unchanged.

### Not done / limits
- `[W]` uses JPL's linearised 3-sigma close-approach bounds. It does not propagate orbits or map keyholes itself; that is what Sentry is for, and why the verdict defers to it.

## [2026-10-22] Kessler cascade watch (proof of concept)

### Added
- **`hannibal_kessler.py` + `[D] Debris cascade`** (also `python hannibal_orbital.py --kessler` or `python hannibal_kessler.py`): reads the public CelesTrak satellite catalog (no key, receive-only, one download cached 12 h through `hannibal_net`) and reports
  - a snapshot of what is in orbit: by type, working satellites, Starlink / OneWeb / Kuiper counts;
  - growth by year since 1960 (in `--json` output);
  - tracked objects per 50 km altitude shell with an unmanaged collision rate, a rough drag lifetime and a **cascade index**: objects in the shell divided by the count at which collision fragments would arrive faster than drag clears them (`N_crit = 2V / (k·σ·v·τ)`);
  - the breakups that left the most tracked debris still in orbit;
  - the energy of a 1 cm aluminium fragment at 10 km/s (~71 kJ, about 20 rifle rounds).
- `test_hannibal_kessler.py`: offline tests (parsing, on-orbit dating, shell binning, lifetime interpolation, the threshold identity, report).

### Verified
- Tests pass; `hannibal_orbital.py` compiles; the `[D]` screen runs through `run_menu` with injected input; a live fetch through `hannibal_net` works.
- Against the 22 Oct 2026 catalog: 35,046 objects in orbit, 17,256 working satellites, 11,151 Starlink. The 450-500 km shell holds 10,386 objects but has index 0.06 (drag clears it in ~5 years). Index passes 1 at 1,150-1,200 km and 1,400-1,600 km.

### Not done / limits
- The model is deliberately simple: k = 100 trackable fragments per collision, 10 km/s, catalog radar cross-section as collision area, rough average-solar-activity lifetimes, no manoeuvring, tracked objects only. Use the index to compare altitudes, not as a forecast. `--fragments` and `--speed` change the two main assumptions.

## [2026-10-11] Integration: one Orbital Directorate, everything merged

### Sources that were merged
| Source | What it contributed |
|---|---|
| `Desktop\hannibal_orbital_directorate` (your running copy, 1 Oct 06:58 + 3 Oct security patch) | the base you actually run, incl. the security patch settings |
| `TELECOM3\Claude outputs\hannibal_orbital_directorate` (1 Oct 09:22) | GEOINT: `hannibal_geoint.py`, `[I] Breach log`, ipapi.co limits, phonenumbers; +89 lines orbital, +34 dashboard, +19 BlueGlobe |
| `hannibal_estimation.py` (4 Oct, Desktop + TELECOM3, identical) | Section V estimator (FRED + Yahoo, threshold model, Newey-West) |
| `patch_orbital.py` 2-3 Oct | JSON-shaped secret masking; home coordinates out of source (patches 1+2, as on your PC; the optional rate-limiter patch 3 stays off, as on your PC) |
| hannibal-satellite 0.1.1 (11 Oct) | the guarded `[E]` Earth-export hook (works once the `hannibal_sat` package is installed next to it) |
| telemetry 1.1.0 + 1.2.0 (11 Oct) | evidence-gated link health, bad-connection handling, NORMAL / LOW INTERNET profiles |

The 09:22 copy was a strict superset of the 06:58 copy (additions only), so it is the base and every later patch was applied on top: all 3 + 1 + 14 anchors matched with nothing left over.

### Added
- **`hannibal_fred.py` + `[M] Macro (FRED)`**: CPI, core CPI, core PCE, fed funds, 10y, 10y-2y, unemployment, M2 velocity, Brent, broad dollar. The FRED key is looked up in `FRED_API_KEY`, then the OS credential store (`python hannibal_fred.py --set-key`), then a key typed in `[M]` (memory only). Sent only to api.stlouisfed.org through `hannibal_net`: masked in every URL/log/error, never in a cache key, never written to disk by Hannibal. FRED's 120 req/min limit is enforced (`api.stlouisfed.org` in `HOST_LIMITS`). The status screen shows whether a FRED key is set. `hannibal_estimation.py` falls back to the same stored key when `FRED_API_KEY` is not set.
- **`hannibal_brain.py` + `hannibal_brain.html` + `[R] Market brain [DEV]`**: what the market is thinking: the ten lobes of the Happiness Formula Architect brain, each carrying one market region (policy, equities, energy, dollar, curve, labour, liquidity, fear & credit, inflation, signal health), a flow field whose speed and density come from real FRED data, and a "what it's thinking" caption that follows the strongest transmission chain (e.g. Energy -> Inflation -> Policy rate -> Yield curve -> Equities).
- **`hannibal_theorem.py` + `[T] Happiness theorem [DEV]`**: the Grand Unified Happiness Theorem and the 10-lobe cranial report, implemented exactly as written, plus a THEOREM card on the market brain page (H_brain, archetype, the ten lobe percentages in lobe colours, component decomposition, canonical equation). The theorem's ten lobes are the market brain's ten lobes (same ids, same order).
  - *Solutions, not rewrites*: inputs that would need a fractional power or square root of a negative number, `Income <= 0`, `tau0 <= 0` or `varpi_pizza <= -200` are refused with the input named; `W_cosmic` (in the canonical equation and the report, not in the detailed formula) is an optional input added after the theorem on its own line; the unbounded theorem is shown raw and as a 0-100 display value; a profile with only recorded results is shown "as recorded", never recomputed.
  - Your profile `brain_profile.json` (The Calibrated Equilibrium, 86.5) is **private**: on your computer and Google Drive only, git-ignored, never in this repository. `brain_profile.example.json` ships instead.
- **Soviet launchers**: `HANNIBAL_NORMAL.bat` (red banner) and `HANNIBAL_LOW_INTERNET.bat` (gold), each with the red-star ASCII art, a Cyrillic line (ОРБИТАЛЬНОЕ УПРАВЛЕНИЕ, КАНАЛ: НОРМА / СЛАБЫЙ) and a slogan (VPERED, K ZVEZDAM! / POYEKHALI!). UTF-8 without BOM, CRLF, `chcp 65001` first.
- `.gitignore` for everything private or machine-specific (profile, audit and breach logs, telemetry report, feeder id, local credentials, caches, builds, backups).

### Security (all layers on when [R] or [T] opens; developers only)
- Developer key gate: PBKDF2-SHA256 hash only, in the OS credential store or an owner-only file in your user profile (never the project folder); 3 wrong tries -> 5-minute lockout; every failure goes to the GEOINT breach log.
- The brain server binds 127.0.0.1 on a random port, refuses any non-localhost Host header (DNS-rebinding guard), opens only with a single-use launch code (60 s) swapped for an HttpOnly SameSite=Strict session cookie (2 h), allow-lists `/`, `/brain`, `/state.json`, refuses POST, and sends a strict Content-Security-Policy with a per-response nonce plus frame-ancestors none, nosniff, no-referrer, no-store.
- Output masking via `hannibal_security_bootstrap`; the FRED key never reaches the page.

### Fixed
- **Home coordinates still in the dashboard**: `blueglobe_dashboard.html` kept your old home coordinates as its fallback config (`patch_orbital` cleaned `hannibal_net.py` and `hannibal_blueglobe.py` but not this one). Now `0, 0 / Home Station`; the real location only ever comes from `/config.json` (`HANNIBAL_HOME_*`). README no longer names a default location.
- A compiled `__pycache__/*.pyc` committed with PR #1 is removed; `__pycache__/` and `*.pyc` are now ignored repo-wide.

### Verified
- Every Python file compiles; `import hannibal_orbital` loads all modules; menu is `1 2 3 4 H N 5 6 7 8 9 G F K I M R T S A Q`.
- The full brain + FRED + security suite: **34 / 34 pass** on the merged tree, including the new [T] entry (FRED screen, key never cached, masking, ten lobes, energy -> inflation chain, quiet and no-data states, bounded activity, dev gate + lockout + breach log, 127.0.0.1 binding, Host check, single-use launch code, HttpOnly cookie, CSP nonce, security headers, forged cookie, POST refused).
- Theorem self-test: **18 / 18 pass** (each term against a hand calculation, the report's x1.16 multiplier is reachable, every refusal, W_cosmic separation, clamp, recorded mode, report layout, lobe ids match the brain).
- Telemetry self-test (16 checks) passes on the merged files; masking self-check (8 cases) passes.
- The brain page with the theorem card rendered in Chromium at 1440 px and 390 px: no console or CSP errors, no horizontal scroll, H = 86.5 "as recorded", 10 lobes.
- Privacy scan of everything committed: no coordinates, phone numbers, names, keys or tokens.

### Not verified
- Not run against live FRED, SatNOGS, Space-Track or N2YO from here (all network paths tested with mocked sessions).
- Launchers checked as text (encoding, line endings, escaping), not run on Windows.
- The `.exe` was not rebuilt; run `build.bat` for the packaged version to pick this up (`hannibal_terminal.spec` already lists the new modules and the brain page).
- Your recorded components (54.3 x 1.16 + 51.6 + 21.7 - 17.1 = 119.2) do not add up to the recorded 86.5 on their own; the report's -22 withdrawal trough plus about -10.7 of financial leakage would close the gap, but the report does not list a leakage line. Shown as recorded, not corrected. Add an `inputs` block to `brain_profile.json` to have Hannibal compute it.
- `[E]` Earth export needs the `hannibal_sat` package, which is not in this repository yet.
