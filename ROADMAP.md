# HANNIBAL — COMPLETE PROJECT ROADMAP

*Original terminal through portable transmission-network forecasting.*
Carried over word for word from `HANNIBAL_V9_PORTABLE/docs/Hannibal_Complete_Project_Roadmap.pdf` (kept in [docs/roadmap/](docs/roadmap/)), with a status column and stage 11 added on 2026-10-11.

## Purpose
A decision-support platform to reduce information asymmetry by connecting real observations to network transmission, friction and calibrated forecasts. It cannot guarantee profits or protection from losses.

## Stages

| Stage | Name | Scope | Status (2026-10-11) |
|---|---|---|---|
| 0 | Original | Markets, news, kinetic strikes, prediction UI, DART/subsea, maps, graphs, weather and infrastructure. | In `hannibal_terminal.py` (root) and V10/V11. |
| 1 | Preserve & secure | Harden storage, network handling, audit and executable trust without breaking feeds or displays. | **Advanced.** Shared masked network layer, JSON-shaped secret masking, home location out of source (dashboard fallback fixed today), keyring for keys, dev-only gates with lockout and breach log. |
| 2 | Friction engine | Validated, deduplicated, confidence/freshness-weighted bounded domain states and interactions. | Equations and corrections in the Equation Reference (beta2 sign, bounded forms); bounded activity map reused by the market brain. |
| 3 | Country matrix | Country markets, headlines, weather, telecom, infrastructure, conflict and local C_t. | Open. |
| 4 | Satellite/weather | Fire, flood, thermal, vegetation, night-light, storm and station observations. | **Orbital Directorate merged into this repo** (`orbital/`): SatNOGS link health (evidence-gated), Space-Track, N2YO, NASA/JPL, BlueGlobe, GEOINT breach log. Earth/Cesium export waits for the `hannibal_sat` package. Planetary defense (2026-10-22): `[W]` impact exclusion for any asteroid/comet (JPL, defers to Sentry) and `[D]` debris cascade watch (CelesTrak) with sensitivity. |
| 5 | Telecom | BGP, IXP, DNS, mobile, backbone, cables, satellites and topology risk. | Telecom node (TELECOM3) separate; offline phone metadata in GEOINT. |
| 6 | Kinetic reintegration | Strikes, naval events, blockades, mobilization and exposure channels. | Open. |
| 7 | Prediction restoration | Fitted asset/horizon models, error gates and deterministic signals. | `hannibal_estimation.py` fits the Section V threshold model on real FRED/Yahoo data. |
| 8 | Transmission networks | Maritime delays, chokepoints, ports, insurance, pipelines, LNG, rail and air cargo. | V9 engine; the market brain draws the macro transmission chain (energy -> inflation -> policy -> curve -> equities) live from FRED. |
| 9 | Portable operation | Speed modes 1–5; Windows/Linux launchers; offline and emergency operation. | **Partly done.** NORMAL / LOW INTERNET launchers (`HANNIBAL_NET_PROFILE`), last-known values when offline, patient retries. Modes 3–5 still open. |
| 10 | Production calibration | Historical warehouse, expansion-window tests, baselines, registry, drift and promotion gates. | Open. |
| 11 | **Macro & market brain** *(new)* | FRED macro board; the ten-lobe market brain ("what the market is thinking"); the Grand Unified Happiness Theorem and cranial report. Developers only. | **Done 2026-10-11**: `hannibal_fred.py` [M], `hannibal_brain.py` [R], `hannibal_theorem.py` [T]. |

## Preservation rules
- Keep DART/subsea nodes, maps, graphs, country selectors, headlines, markets, weather, satellites, telecom, kinetic monitoring and prediction.
- Security failures must be visible degraded states; never silently fabricate replacement data.

## Evidence pipeline
- Source → validation → canonical event → deduplication → corroboration → freshness → geography/network mapping → domain state.
- Always report estimate, confidence, freshness, source count and quality flags separately.

## Domains
- Energy, transport, money, labor, infrastructure, weather, conflict, markets, telecom, kinetic, maritime, pipeline, port, rail, air cargo, insurance and logistics delay.

## Country intelligence
- Selection updates local markets, headlines, weather, satellite, telecom, logistics and C_t together.
- Global observations may propagate locally according to exposure; inferred geography carries lower confidence.

## Transmission graph
- Kinetic shock → energy/infrastructure exposure → chokepoint/pipeline/port impairment → transit delay/insurance → energy logistics → inflation/assets.
- Critical chokepoints: Hormuz, Suez, Panama, Bab el-Mandeb, Malacca, Bosporus, Gibraltar and English Channel.

## Forecasting
- Fit separate assets and horizons from real historical forward returns.
- Suppress BUY/SELL when predicted magnitude does not exceed model RMSE or threshold.
- LLM explains structured output only; it cannot calculate or override.

## Portable profiles
- 1 Full; 2 Balanced; 3 Legacy Hardware; 4 Offline Analysis; 5 Emergency Mode.
- Legacy uses one worker, reduced history and slow refresh, disabling heavy visual/satellite work while retaining core markets, headlines, telecom, weather and friction.

## Completion gates
- Versioned historical warehouse with provenance and revisions.
- Leak-free feature tables and expanding-window evaluation against naive/autoregressive/single-factor baselines.
- Promote only stable out-of-sample improvement; monitor data, source and model drift.

## Target operating flow
```
REAL SOURCES
 -> validated observations
 -> deduplicated/corroborated events
 -> geography + network topology
 -> confidence/freshness
 -> bounded domain states
 -> kinetic/transmission merge
 -> interactions
 -> inflation/risk/liquidity/growth models
 -> global + country C_t
 -> asset forecasts + uncertainty
 -> deterministic signal
 -> explanation
```

## Next up (open items from the 2026-10-11 work)
1. Run both launchers on Windows and rebuild the `.exe` with `build.bat`.
2. Live first run of [M] / [R] with the FRED key; watch the 15-minute brain refresh and 6-hour FRED cache.
3. Bring the `hannibal_sat` package (Earth/Cesium export, CelesTrak TLEs) into `orbital/` so [E] lights up; use its CelesTrak TLEs as the fallback when a Space-Track epoch is stale.
4. Optional rate-limiter fix (patch_orbital patch 3) if multiple threads start sharing one host.
5. Portable modes 3–5 on top of the LOW INTERNET profile.
6. Give the theorem real inputs (`inputs` block in `brain_profile.json`) so H_brain is computed rather than recorded.
7. Reconcile the two terminals (root `hannibal_terminal.py` and `orbital/hannibal_terminal.py`) into one.

## Validation boundary
Live endpoints, credentials, real topology data and aligned historical training data were not supplied. Generated modules were syntax-checked, but live operation and fitted forecast performance are not claimed.
