# Orbital Directorate changelog

Newest first. What changed, why, what was verified, and what was not.
Telemetry 1.1.0 / 1.2.0 detail: [CHANGELOG_telemetry.md](CHANGELOG_telemetry.md).

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
