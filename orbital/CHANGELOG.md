# Orbital Directorate changelog

Newest first. What changed, why, what was verified, and what was not.
Telemetry 1.1.0 / 1.2.0 detail: [CHANGELOG_telemetry.md](CHANGELOG_telemetry.md).

## [2026-10-16] New: Moonbounce (EME) link budget -- `[E]` / `--eme`

### What it is
The Moon is a passive natural reflector. Transmit at it on an amateur band you are licensed for and
~2.5 s later your own signal comes back, ~250-270 dB weaker. The new `hannibal_eme.py` works out whether
your station could actually hear that echo, using the Moon's live range and range-rate over your home
(JPL Horizons, the same source as `[5]` Sky tonight -- no key needed).

### Added
- **`hannibal_eme.py`** -- pure, testable physics:
  - path loss `L = (4*pi)^3 R^4 / (lambda^2 * sigma)` with the Moon's radar cross-section (albedo ~6.5%);
  - parabolic-dish gain `G = eta (pi D / lambda)^2`;
  - two-way Doppler `f_d = -2 f0 v/c` (sign: receding Moon -> echo lower) to tune the SDR;
  - thermal noise `N = k_B T_sys B` and coherent processing gain `10 log10(B*tau)`;
  - SNR reported in a 2500 Hz reference bandwidth (the WSJT-X convention) and compared against the
    published decode thresholds of Q65 / JT65 / FT8 / CW / SSB for an honest "can you hear it" verdict.
  - `current_moon()` reads az/el, range and range-rate from Horizons through the masked, cached,
    rate-limited `hannibal_net` layer.
- **`[E]` menu entry and `--eme` flag** in `hannibal_orbital.py`: prompts for band, dish and power (sensible
  23 cm defaults, overridable with `HANNIBAL_EME_*` env vars), then prints the full budget: Moon position
  and whether it is up, range, round-trip time, every line of the link budget, the Doppler to tune to, the
  echo-depth smear, and the mode ladder with the verdict.
- **`test_hannibal_eme.py`** -- 6 offline tests pinning the physics (252/271 dB path loss, dish-gain f^2
  scaling, Doppler sign and magnitude, 2.56 s round trip, 11.6 ms depth, noise floor, verdict flips).

### Verified (offline + one live read)
- All 6 tests pass. Live read over Antwerp (23 cm, 3 m dish @55%, 300 W, Tsys 100 K): echo received
  ~-162 dBm against a ~-145 dBm noise floor -> SNR ~-17.6 dB in 2500 Hz -> detectable with Q65/JT65/FT8,
  not CW by ear. A single 2 m yagi comes out ~-38 dB (no echo); a 10 m / 1 kW dish ~+13 dB (SSB-capable) --
  all matching real-world EME experience.

### Notes / not done
- Transmit figures assume you hold the licence and may use the band. The verdict is a model, not a promise:
  it does not include ground/sky-noise pointing geometry, the exact libration coherence time, or non-reciprocal
  Tx/Rx paths. `l_misc` (default 4 dB) lumps feedline, Faraday/polarisation, pointing and atmosphere.
- Depends on the home-location fix (needs `home_line` / `home.set`); stacked on that branch.

## [2026-10-16] Fix: "overhead now" was silently computed for 0N 0E

### What was wrong
`hannibal_net.home_location()` fell back to latitude 0, longitude 0 (the Gulf of Guinea) whenever
`HANNIBAL_HOME_LAT` / `HANNIBAL_HOME_LON` were not set, and nothing on screen said so. Every
observer-dependent screen used that point: `[H]` home window, `[N]` > Military / Globalstar / any category
overhead, `[5]` sky tonight, Horizons observer ephemerides, satellite passes, and the BlueGlobe home marker.

How it showed up: a real run listed "MILITARY OVERHEAD NOW (113 above the horizon)" with geostationary
satellites (UFO, DSCS, AEHF 2, SKYNET 5C, SICRAL 1B, LUCH) at 55-85 deg elevation. The table's own columns
gave it away: DROR-1, sub-point 0.0, -4.0, "GROUND km 450" = exactly 4 deg from 0N 0E. From a mid-latitude
European home (~51N) no geostationary satellite can rise above ~31 deg. The orbital math was right; only the
observer was wrong.

### What changed
- `hannibal_net.home_location()` now looks up the home in this order, first match wins:
  1. `HANNIBAL_HOME_LAT` **and** `HANNIBAL_HOME_LON` (+ `_ALT_KM`, `_NAME`) environment variables, as before;
  2. **new** `~/.hannibal/home.json` in your user profile (owner-only; never in the project folder);
  3. nothing set: still 0, 0 so nothing crashes, but marked `set=False` and named `HOME NOT SET (0N 0E)`.
  The result also carries `source` (`environment`, the file path, or `unset`).
- **New** `python hannibal_orbital.py --set-home LAT LON NAME` writes `~/.hannibal/home.json` once
  (decimal degrees, north/east positive; range-checked). Can be combined with `--home`, `--sky`, etc.
  `hannibal_net.save_home()` is the same thing for code. Honors `HANNIBAL_VAULT_DIR` like the credential vault.
- Every overhead table now prints the observer under its title (`Observer: NAME (+lat, +lon)`), or a red
  `[!] NO HOME SET: using 0N 0E. Fix: ...` line. The home window shows it once, under its header. The sky
  screen shows the same warning. `--status` reports the home and where it came from, or `NOT SET` in red.
- BlueGlobe (`hannibal_blueglobe._config_payload`) now uses `home_location()` too, so a saved home reaches
  the 3D globe (served on 127.0.0.1 only, as before). Falls back to the old env-only lookup if the import fails.
- Partial environment (only `HANNIBAL_HOME_LAT` set) no longer silently pairs it with longitude 0: it is
  ignored and the saved file (or the warning) applies.
- No coordinates added to source: this repository is public.

### Verified (offline, in a clean environment)
- nothing set -> `set=False`, home window / sky / overhead tables / `--status` all show the warning;
- `--set-home 151 4 X` refused (rc 2), `--set-home 51` refused (rc 2); a valid call writes `home.json`
  with mode 0600 and every screen then shows `Observer: <name>`;
- both env vars set -> env wins; only one set -> file wins;
- BlueGlobe payload picks up the saved home;
- spherical check with the module's own `elevation_deg`: from 51.2N the best possible geostationary
  elevation is 31.4 deg (DROR-1 at 0, -4 would be 30.8 deg, 5,750 km ground distance).

### Not verified
- A live N2YO `above` call from the new home (needs your N2YO key, which never leaves your machine).
- The frozen `.exe`: rebuild it (`build.bat`) to pick this up; an old build keeps the old behaviour.

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
