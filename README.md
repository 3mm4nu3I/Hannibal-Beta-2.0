# PROJECT HANNIBAL

**A receive-only, open-data intelligence terminal in Python.** Hannibal reads public sources
(NASA/JPL, SatNOGS, Space-Track, CelesTrak, N2YO, FRED, Yahoo Finance, SEC EDGAR) and turns them
into readings that are reproducible and carry their uncertainty. It covers orbital awareness,
planetary defence, satellite reception and market conditions. It never transmits, and it never
fills a gap with invented data.

> *Hannibal ad portas.* The name is the Roman alarm for a threat at the gates. This system watches
> those gates.

---

## Executive summary

Hannibal started in mid-2026 as a market terminal that combined live prices with open-source news
(conflict, labour, weather, shipping). Over four months it grew into a modular telemetry station.
The project rests on three engineering commitments:

1. **Evidence over appearance.** Every reading states its source, its sample size and its
   uncertainty. A failed source shows as a visible degraded state, and Hannibal never substitutes
   a guess. A small sample is labelled `LOW SAMPLE`, and a feed it cannot reach is shown with `*`
   as its last known value.
2. **One hardened network layer.** All network traffic in the orbital modules goes through a
   single client. That client masks secrets, caches on disk, enforces each provider's published
   rate limits and retries with back-off. Credentials never reach a log, a cache file or the
   screen.
3. **Reproducibility.** Results that matter ship with the data and scripts that produced them, and
   every change is logged with what was verified and what was not.

| | |
|---|---|
| Language | Python 3 (standard library + `requests`, `numpy`, `pandas`, `cryptography`, `keyring`) |
| Size | about 22,000 lines across 55 Python files (includes archived iterations of the terminal) |
| Interfaces | text terminal, interactive menus, CLI flags, a local 3D globe dashboard (browser), PDF reports |
| Platforms | Windows (primary, PyInstaller `.exe` via `build.bat`), Linux/macOS from source |
| Tests | 7 offline suites, all passing (see [Verification](#7-verification)) |
| Licence posture | receive-only; see [Receive-only and the law](orbital/README.md#receive-only-and-the-law-belgium) |

---

## 1. Design principles

Taken from the project [roadmap](ROADMAP.md) and enforced in code:

- **Security failures are visible, degraded states.** Nothing is silently replaced. If a quote is
  missing, the row says `NO LIVE QUOTE`.
- **Evidence pipeline:** source → validation → canonical event → deduplication → corroboration →
  freshness → geography/network mapping → domain state. Estimate, confidence, freshness, source
  count and quality flags are reported separately.
- **The LLM explains and never computes.** Where a language model is used (a local Ollama model
  in the terminal's chat), it explains structured output and cannot calculate or override a result.
- **Receive-only.** Hannibal reads public records. It decodes no traffic and transmits nothing.

## 2. Architecture

```
  PUBLIC SOURCES                         HANNIBAL                                  OUTPUTS
  ---------------------------------      ----------------------------------------  ----------------------
  NASA/JPL  (Horizons, CAD, Sentry,  --> hannibal_net.py  shared HTTP layer        terminal screens
             SBDB, sb_sat, sb_radar)       - secret masking (URLs, params, errors) menus  [W] [Z] [D] [E] ...
  SatNOGS DB + Network                     - on-disk cache with per-call TTL       CLI  --neo --zombie ...
  Space-Track  (TLE, DECAY, TIP, CDM)      - per-host throttling (provider policy) 3D globe (localhost)
  CelesTrak SATCAT                         - retries / Retry-After / stale-serve   JSON exports
  N2YO REST                                        |                               PDF mission reports
  FRED, Yahoo Finance, SEC EDGAR                   v
                                         domain modules (pure functions, tested)
                                         neo | zombie | kessler | eme | telemetry
                                         fred | estimation | brain | geoint
```

The domain modules keep their maths in pure functions with no network access and no globals, so
the physics and statistics are unit-tested offline. Only a thin `fetch()` layer touches the network,
and it always goes through `hannibal_net`.

## 3. Capabilities

| Key | Module | What it answers | Source | Method |
|---|---|---|---|---|
| `[W]` | `orbital/hannibal_neo.py` | Can this asteroid or comet hit Earth? | JPL CAD, Sentry, SBDB | Each close approach to 2200 is tested at the near edge of JPL's 3-sigma window against Earth's radius + 100 km. The verdict always defers to Sentry, because a clean pass can still lead through a keyhole to a later impact. |
| `[Z]` | `orbital/hannibal_zombie.py` | Which satellites on a list still transmit something hearable? | SatNOGS DB + Network | Evidence tiers (HEARD / LISTED, NOT HEARD / NO ACTIVE TX / NOT IN SATNOGS / NOT CHECKED). An unreachable network turns the result into a lower bound, never a clean zero. |
| `[D]` | `orbital/hannibal_kessler.py` | Which orbital shells are near a debris cascade? | CelesTrak SATCAT | A linearised Kessler threshold per 50 km shell, `N_crit = 2V / (k·σ·v·τ)`, plus the factor the roughest assumptions must be off by to flip each shell's status. A proof of concept. |
| `[E]` | `orbital/hannibal_eme.py` | Can my station hear its own echo off the Moon? | JPL Horizons (live Moon range) | Full EME link budget: radar path loss, dish or Yagi-array gain, per-band system noise (receiver + galactic sky + lunar + ground), two-way Doppler. |
| `[1]`/`[L]` | `orbital/run_telemetry.py` | Is each satellite in my fleet being heard? | SatNOGS, Space-Track | Link health with 95% Wilson intervals, `LOW SAMPLE` below 8 observations, station failures excluded, stale TLEs flagged. |
| `[V]` | `orbital/hannibal_orbital.py` | What is above me now? Re-entries, conjunctions, any body's ephemeris | Space-Track, N2YO, JPL | Rate-limit-aware clients; USSR/CIS objects highlighted. |
| `[M]` | `orbital/hannibal_fred.py` | Macro board: CPI, core PCE, rates, curve, M2 velocity, Brent, dollar | FRED | API key read from env or the OS credential store. Never in source. |
| — | `orbital/hannibal_estimation.py` | Does the threshold model hold on real data? | FRED, Yahoo Finance | Additive and log threshold specifications fitted with Newey-West (HAC) errors and Breusch-Godfrey lag selection. Prints real fitted results only. |
| `[R]` | `orbital/hannibal_brain.py` *(dev)* | "What the market is thinking" | FRED + telemetry | Ten market regions scored by z-scored recent moves, drawn as a live browser view on `127.0.0.1` only. |
| `[I]` | `orbital/hannibal_geoint.py` | Incident record for probes against Hannibal itself | own logs, `ipapi.co`, `phonenumbers` | Enriches only events already in its own log. It cannot be used as a general lookup on third parties. Phone metadata is parsed offline. |
| — | `hannibal_terminal.py` | Market + OSINT terminal | Yahoo Finance, SEC EDGAR, news feeds | Composite friction index, SEC token-bucket limiter, encrypted SQLite intel log, local-LLM chat. |

## 4. Security and data integrity

- **Secret masking.** `secret_masking.py` registers every credential at runtime and scrubs it
  from stdout, stderr, logging, URLs, exception text and cached payloads (`HANNIBAL_NO_MASK=1`
  to disable when debugging). It has one known false positive, documented in
  [orbital/README.md](orbital/README.md#masking).
- **Credentials.** Hannibal checks environment variables first, then the OS credential store via
  `keyring`, then a memory-only value typed for this run. Passwords are typed hidden. A pty test
  checks that a typed password is never echoed, printed or written to disk.
- **Developer gate.** Developer pages sit behind a PBKDF2-hashed key with lockout, a single-use
  launch code, a strict CSP on the local server, and a breach log of failed attempts.
- **Encryption at rest.** The terminal's intel log uses Fernet with a PBKDF2-derived key.
- **Provider policy.** Space-Track (<30/min, <300/h, GP hourly, SATCAT daily), N2YO (90/900 per
  hour), JPL (1 s spacing) and SEC EDGAR fair-access limits are enforced client-side and backed by
  caches.
- **Integrity checks.** `MANIFEST_SHA256.json` holds checksums for the portable V10/V11 builds.
  Patchers (`patch_hannibal.py`, `patch_telemetry.py`) are all-or-nothing, dry-run by default,
  write backups and can `--revert`.

## 5. Case study: mission of 22–23 October 2026

The full report is in [docs/reports/2026-10-23_mission-report/](docs/reports/2026-10-23_mission-report/)
(9-page PDF). Every figure in it is rebuilt from `calcs.json` and the JSON exports beside it.

- **Zombie satellites over Antwerp.** Of 148 military objects overhead, **2 were heard**
  (95% range 0.4–4.8%) and **0 have an uplink on record**. One of the two is ERS 15, launched in
  1966 and still putting out a CW carrier at 136.439 MHz.
- **ERS 15 reception history.** 632 vetted good SatNOGS observations since 21 Oct 2020 by at
  least 96 stations. It was heard on **31.0%** of vetted passes over the last 365 days
  (71 of 229; 95% range 25.4–37.3%).
- **Apophis (99942), 13 April 2029.** `[W]` ran against JPL orbit solution 220 (7,370
  observations over a 6,599-day arc). Closest approach is **38,011 km from Earth's centre**, and
  JPL's 3-sigma window spans 38,008–38,015 km. That leaves **31,530 km above the atmosphere** at
  the near edge. Sentry removed Apophis from its risk list on 21 Feb 2021. Verdict: **excluded to
  2200**. The project treats any challenge to the published 2029 distance as a testable claim:
  `[W]` re-runs against every new JPL orbit solution, and the figures above are what the current
  data says.
- **Voyager 1 link budget.** At 172.69 au, the one-way light time is 23 h 56 min. The free-space
  formula used here reproduces JPL's published Voyager design table to 0.01 dB.

**Corrections recorded in the report itself.** The reception evidence comes from SatNOGS volunteer
stations, not from Hannibal's own antenna. Hannibal is not air-gapped (it uses public internet
APIs). ERS 15 was documented as transmitting before this work.

## 6. Running it

```bash
pip install -r orbital/requirements.txt
python orbital/hannibal_orbital.py --set-home 51.22 4.40 Antwerp   # once; stored in ~/.hannibal/
python orbital/hannibal_orbital.py          # Orbital Directorate menu
python orbital/hannibal_neo.py 99942        # impact exclusion, no key needed
python orbital/hannibal_zombie.py           # who still transmits, no key needed
python orbital/hannibal_kessler.py          # debris cascade watch, no key needed
python hannibal_terminal.py                 # market / OSINT terminal
```

`orbital/HANNIBAL_NORMAL.bat` and `orbital/HANNIBAL_LOW_INTERNET.bat` start Hannibal with the
normal or the poor-connection network profile. `build.bat` produces the Windows executable.
Logins and keys are described in [orbital/README.md](orbital/README.md#where-do-i-type-my-passwords).

## 7. Verification

Offline suites, all passing on 25 Oct 2026:

| Suite | Covers |
|---|---|
| `orbital/test_hannibal_neo.py` | pass geometry, Sentry states, the keyhole case, verdicts, a fake network |
| `orbital/test_hannibal_zombie.py` | targets, evidence tiers, windows, page caps, unreachable network |
| `orbital/test_hannibal_kessler.py` | snapshot, growth, shells, physics, threshold, sensitivity |
| `orbital/test_hannibal_eme.py` | 14 link-budget tests (gain, noise, Doppler, Yagi arrays) |
| `orbital/test_hannibal_altguard.py` | N2YO altitude sanity guard |
| `test_hannibal_subsea_spatial.py` | spatial calculations, DART buoy parser |
| `test_volcano_anomaly.py`, `run_evidence_confidence_fixtures.py` | baseline anomaly score (warm-up, spikes, caps, persistence), evidence-confidence gate |

**Verified against live services:** JPL Horizons, `sb_sat`, `sb_radar`, periodic orbits, a full
SatNOGS scan, the Space-Track login with DECAY/TIP/BOXSCORE/GP/CDM, and every N2YO endpoint used.

**Not verified live:** the BlueGlobe dashboard against the real `blueglobe.js` (it needs a
whitelisted key), the ADS-B feeder (stand-in server only), and out-of-sample forecast performance.
No forecasting accuracy is claimed.

## 8. Limitations and open work

- Two terminals still exist (`hannibal_terminal.py` at the root and `orbital/hannibal_terminal.py`)
  and need reconciling into one ([roadmap](ROADMAP.md) item 7).
- The portable V10/V11 builds import from a `core/` folder that is not in this repository.
  Run them from the full portable package. In `MANIFEST_SHA256.json`, the two `.bat` hashes are
  for LF line endings, while a git checkout gives CRLF.
- `[D]` is a deliberately simple, linearised model. It ignores manoeuvring and untracked debris,
  and it says so in its output.
- "Not in SatNOGS" is not proof that a satellite is dead, and "heard" is not proof that it can be
  commanded.
- Production calibration (a versioned warehouse, expanding-window tests against baselines, drift
  monitoring) is still open ([roadmap](ROADMAP.md) stage 10).

## 9. Repository map

```
hannibal_terminal.py            market / OSINT terminal (current)
orbital/                        Orbital Directorate: every space module, its tests, launchers, README
docs/reports/                   mission reports with their data and build scripts
docs/changelogs/, docs/roadmap/ release notes and roadmap PDFs
CHANGELOG.md, ROADMAP.md        what changed (and what was verified); where it is going
VolcanoLlamaNapalm.py, *_pre_*  archived iterations kept for history
```

## How this was built

Hannibal is designed, directed, tested and operated by **Bram Noffels**: the architecture, the
requirements, the scientific framing, live testing on real accounts and hardware, and every
decision about what ships. Much of the code was written with AI coding assistants under that
direction. Each change is recorded in [CHANGELOG.md](CHANGELOG.md) with what was changed, why,
and what was and was not verified.

**Author:** Bram Noffels, Antwerp · [github.com/3mm4nu3I](https://github.com/3mm4nu3I)
