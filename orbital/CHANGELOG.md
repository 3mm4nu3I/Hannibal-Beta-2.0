# Orbital Directorate changelog

Newest first. What changed, why, what was verified, and what was not.
Telemetry 1.1.0 / 1.2.0 detail: [CHANGELOG_telemetry.md](CHANGELOG_telemetry.md).

## [2026-10-23, late night] Independent cross-check: NASA/JPL vs ESA NEOCC, with an evidence trail

### Why
To decide whether there's real reason for concern about Apophis, one source asked many times isn't enough. ESA's NEO Coordination Centre fits its own orbit with its own software, so agreement between ESA and JPL is much stronger evidence.

### Added
- **`hannibal_crosscheck.py`** (`python hannibal_crosscheck.py 99942 --evidence DIR`). Fetches JPL's close approaches, Sentry and SBDB, and ESA's `.clolin` close approaches, risk list and observation file, all live: no cache, no stale fallback. Every raw reply gets a SHA-256 hash, and small replies are saved verbatim with `SHA256SUMS` and `manifest.json`. Passes are matched across agencies (JPL TDB converted to UTC). Each pass is AGREE when the two distances are within 3 combined sigma. Verdict: CONSISTENT, CONCERN (risk-list listing, a minimum distance inside Earth + 100 km, or a 3-sigma disagreement where the window is smaller than the distance), or NO DATA.
- `test_hannibal_crosscheck.py` (offline, trimmed real JPL/ESA replies). Every concern trigger is tested on its own, as is the rule that no data never becomes an all-clear, and that the evidence hashes match the saved bytes.
- `docs/investigation/apophis/PREREGISTRATION.md`: the question, the baseline, criteria C1 to C5 fixed in advance, what would refute the concern, and what to do if a criterion fires. `seal.py` is a commit-reveal hash, so a hypothesis can be registered now and revealed later.
- Daily brief: new section 1b (JPL vs ESA), evidence saved per run to `docs/investigation/apophis/evidence/<stamp>/`. C1 to C5 raise alerts.

### Verified (live, 23 Oct 2026)
- 2029: JPL 38,011 km vs ESA 38,014 km, 2.3 km apart = 1.4 sigma: AGREE. Both agencies put closest approach at the same minute, 21:45 UTC (21:44:50 vs 21:45:03).
- All nine shared passes to 2116 AGREE. ESA lists three distant passes (2109 twice, 2124, 18 to 27 million km) that JPL's close-approach list doesn't have; these are shown as "ESA only".
- Neither risk list carries Apophis. Both have the last observation on 2022-04-09.

## [2026-10-23, night] `[L]` Where it will be: flyby track, 3-sigma envelope, impact-off-Lisbon test

### Why
`[W]` says where an asteroid won't be (Earth). The other half: where it will be, minute by minute, how sure JPL is at each pass, and a test that can prove a specific impact impossible. The test case is an impact in the Atlantic off Lisbon.

### Added
- **`hannibal_neo_where.py` + `[L] Where it will be`** (also `python hannibal_orbital.py --neo-where 99942` or `python hannibal_neo_where.py 99942 --target LAT LON NAME`). Uses NASA/JPL Horizons observer tables with 3-sigma covariance (through `hannibal_net`, cached 6 h, no key) plus the `[W]` close-approach list and Sentry status.
  - TRACK: every minute for 3 h either side of the closest pass. Shows the distance, the point on Earth it is over (sub-point, from Greenwich apparent sidereal time), the magnitude, and the 3-sigma box (along x across the sky, +/- range) in km.
  - ENVELOPE: the same box at every close approach to 2200.
  - IMPOSSIBLE-EVENT TEST: a topocentric table for one surface point (default 38.70N 9.60W, off Lisbon) over +/-12 h. Gives the closest approach to the point and the nearest 3-sigma edge. IMPOSSIBLE when that edge stays above the atmosphere. Also reports when the object is above the horizon there and when it is up in a dark sky. If Sentry still lists the object, or Sentry is unreachable, the report says the result covers this flyby only.
- `test_hannibal_neo_where.py` (offline, trimmed real Horizons tables, fake network).

### Changed
- `[W]` labels its dates as TDB, which is what JPL's close-approach data uses, and notes the offset. Apophis's "21:46" is 21:46:13 TDB = 21:45:03 UTC.

### Verified (live, 23 Oct 2026, orbit 220)
- Apophis closest at 21:45 UTC on 13 Apr 2029: 38,015 km from the centre, over 29.0N 43.1W (mid-Atlantic). 3-sigma box 2.5 x 1.7 km, +/-3.3 km.
- Sub-point check: Horizons, asked for the view from the computed point, puts Apophis at 89.8 deg elevation.
- Off Lisbon: closest 32,495 km at 21:39 UTC, nearest 3-sigma edge 32,492 km, so 32,392 km above the atmosphere. IMPOSSIBLE. It is up in a dark sky there from 19:41 UTC, peaking at magnitude 2.8.
- Envelope: 2051 box 221,280 x 49 km (+/-237,314); 2102 1.9 million x 207 km; 2116 10.3 million km (rough).
- All orbital tests pass.

### Not done / limits
- The boxes are Horizons' linearised covariance, which can't be trusted for the 2116 pass (marked ~rough). For that pass Sentry decides.
- UT1-UTC is ignored in the sub-point (< 0.004 deg of longitude).
- Not added to `hannibal_terminal.spec` hidden imports, the same as `[W]` (see the note further down).

## [2026-10-23, later] Moonbounce: choose dish or Yagi, band-aware noise

### Why
Three weaknesses in `[E]`: every band assumed the same 100 K system noise (fair on 23 cm, far too optimistic on 2 m and 6 m, where the galactic sky dominates); the screen printed a +51.8 dB "processing gain" that reads like part of the budget but is not; and the only antenna was a dish, which nobody uses for EME on 6 m or 2 m.

### Added
- **Antenna choice on any band** (`hannibal_eme.py`, `[E]`): a dish of a chosen kind (`prime-focus` 55% efficiency / 20 K ground pickup, `offset` 65% / 10 K, `mesh` 45% / 25 K; typical values) and diameter, or an array of N Yagis (gain of one Yagi; +10·log10(N), less 0.5 dB phasing loss when N > 1). Defaults: 4 Yagis on 6 m (12 dBi each), 2 m (15 dBi) and 70 cm (18 dBi); a 3 m prime-focus dish on 23 cm and up. The beamwidth is printed next to the gain.
- **System noise worked out per band and antenna**: receiver 40 K + sky (2.7 K + 200 K × (f / 144 MHz)^-2.55, the galactic background away from the Milky Way's plane) + the Moon's own 210 K glow times the share of the beam it fills + ground pickup. Enter at the Tsys prompt takes it; a typed number or `HANNIBAL_EME_TSYS_K` still sets a fixed total. The breakdown is printed next to the noise floor.
- New settings: `HANNIBAL_EME_ANTENNA`, `_DISH_KIND`, `_YAGI_DBI`, `_YAGI_N`, `_TRX_K`, `_TGROUND_K`, `_SKY144_K`.
- 8 new tests in `test_hannibal_eme.py` (14 in all), including the `[E]` screen driven with the Moon stubbed out.

### Changed
- The processing-gain line is labelled "theoretical ceiling only, NOT added to the SNR", with the reason. It never was in the SNR; now the screen says so.
- "Dish gain" is now "Antenna gain"; a dish chosen on 6 m / 2 m / 70 cm gets a one-line note that EME stations there normally use Yagi arrays. An unknown band falls back to the default band with a warning instead of a mismatched label.
- `station_defaults()["t_sys_k"]` is `None` unless `HANNIBAL_EME_TSYS_K` is set (auto noise); `["efficiency"]` is `None` unless `HANNIBAL_EME_EFF` is set (the dish kind decides).

### Kept working
- A bare number at the antenna prompt still means a prime-focus dish of that diameter, so `RUN_EME.bat`'s piped answers (`23cm`, `3`, `300`, `100`) give exactly the same result as before. Tested.

### Verified
- All 14 EME tests and the other orbital tests pass; root fixtures pass.
- Live over Antwerp, 23 Oct 16:20 UT (Moon up, el +9°, 379,310 km): `RUN_EME.bat`'s answers → 3 m dish, Tsys 100 K set, SNR −16.4 dB, Q65; 2 m, 4 × 15 dBi Yagis, 300 W, auto Tsys 273 K (receiver 40 + sky 202 + Moon 0 + ground 30) → SNR −19.8 dB, Q65.
- The noise fix in numbers: that 2 m array looked 4.3 dB better with the old fixed 100 K. On 23 cm the auto figure (65 K) is lower than the old 100 K, so a typed 100 K is the more cautious choice there.

### Not done / limits
- Sky noise assumes the Moon is away from the Milky Way's plane; near it the 2 m figure can be three times higher (`HANNIBAL_EME_SKY144_K`). Not computed from the Moon's position yet.
- No libration spreading of the echo (matters on 3 cm and up), no Faraday rotation model on 2 m (inside the 4 dB misc loss), no ground gain for Yagis at low elevation.
- Yagi gains, dish efficiencies and ground pickup are typical values, not measurements of any real antenna.

## [2026-10-23] Sync: the laptop's work merged into main

### Why
The running copy on the laptop (`Desktop\hannibal_orbital_directorate`) and main had drifted apart. The laptop had the 16-17 Oct work, which lived only on branch `feature/eme-moonbounce` and was never merged: the home-location fix, `[E]` Moonbounce (EME) and the N2YO altitude guard. Main had `[W]`, `[D]` and `[Z]`, which the laptop lacked. Checked first: the laptop's files match `feature/eme-moonbounce` byte for byte (`hannibal_net.py` and `norad_targets.json` compared directly, every other changed file by size).

### Changed
- Merged `feature/eme-moonbounce` into main (merge commit, no history rewritten). Backup of main before the day's merges: branch `backup/main-2026-10-23-pre-sync`.
- One conflict, in this changelog: both sides' entries kept, newest first. `hannibal_orbital.py`, `hannibal_net.py`, `hannibal_n2yo.py`, `hannibal_blueglobe.py` and `README.md` merged without conflicts. `[E]` added to the what's-new table.

### Verified
- Every Python file compiles; menu is `1 2 3 4 H N 5 E 6 7 8 9 W Z D G F K I M R T S A Q`, no duplicate keys or command-line flags.
- All five orbital tests pass (`altguard`, `eme`, `kessler`, `neo`, `zombie`), plus the root subsea/spatial and evidence-confidence fixtures.
- `[Z]`, `[W]` and `[E]` driven through the merged menu / CLI: zombie check on ERS 15 (heard), Apophis EXCLUDED, EME link budget runs to a verdict.

### Not done / limits
- The optional Earth-export add-on (`hannibal_sat`, not in this repository) also registers `[E]`. With it installed, the two would share a key. It is not installed on the laptop or here, so nothing clashes today; this predates the merge.

## [2026-10-23] Receive-only and the law (README)

### Added
- `README.md`: a "Receive-only and the law (Belgium)" section from the Orbital Directorate's regulatory memo of 22 Oct 2026: no licence needed to own or use a receiver; licences (ON3 and up) only for transmitting; the UBA ONL listener number is voluntary. Plus the one rule the memo left out: BIPT allows listening only to frequencies open to everyone or ones the frequency holder has authorised, so military satellite traffic stays off limits and TETRA / speed-radar detectors are banned outright.

### Verified
- Against BIPT's consumer pages on 22 Oct 2026 (linked in the section). The UBA ONL price and terms were not confirmed; the section says to check uba.be.

### Not done / limits
- Not legal advice. Documentation only; no code changed.

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

## [2026-10-17] Fix: reject non-physical satellite altitudes from N2YO (overhead + detail)

### The bug
A live overhead run over Antwerp printed **USA 568 (NORAD 66551)** with an altitude of
**2,408,092,187,602 km** (~2.4 trillion km, i.e. ~16,000 AU). That is not a real orbit and not a
run-timing artifact: the `above` list takes `alt_km` straight from N2YO's `satalt` field
(`hannibal_n2yo.above()`), evaluated at a single instant -- nothing is integrated "while the tally
runs", and no real motion covers trillions of km in the ~15 s of a run. The cause is upstream: N2YO
served a `satalt` propagated from a **degenerate / immature element set** -- near-zero mean motion, or
eccentricity >= 1 (a parabolic/hyperbolic "escape" solution) -- which drives the derived altitude to
absurd values. 66551's very high NORAD id is consistent with a freshly catalogued object whose TLE is
not yet well fit. The module simply passed the number through, and because elevation is computed
*locally* from that altitude, the bad object still got a plausible-looking elevation (27.9 deg) and
sat in the list looking authoritative.

### Fixed
- **`hannibal_n2yo.py`** -- new `ALT_MAX_KM = 500,000` ceiling and `sane_alt_km(alt)` helper. Any
  altitude that is missing, non-finite (NaN/inf), negative, or above the ceiling is treated as
  unusable: `alt_km` becomes `None` and the row is flagged `alt_suspect=True`. The ceiling sits well
  above every real orbit we carry (VELA pair ~160,000 km near apogee; the Moon itself is ~384,400 km)
  so nothing legitimate is clipped, while 10^12 km is rejected outright.
  - `above()`: suspect rows keep their identity, sub-point and ground distance (they are still "above"
    per N2YO's own server-side filter) but get **no geometric elevation** (`el=None`, since a bad
    altitude makes the elevation meaningless) and **sink to the bottom** of the list.
  - `position()`: the `[S]` satellite-detail lookup flags a suspect altitude the same way. N2YO's own
    reported elevation there is left untouched (it does not depend on `satalt`).
- **`hannibal_orbital.py`** -- the overhead table and the satellite-detail screen now render a suspect
  altitude/elevation as `?` and append `[suspect TLE: altitude rejected]`, instead of crashing on
  `None` or printing a trillion-km figure as if it were real. Column alignment preserved.

### Verified
- **`test_hannibal_altguard.py`** (new, 5 offline tests, all pass): `sane_alt_km` accepts LEO/GEO/VELA/
  lunar distances and rejects 2.4e12 km, the ceiling+0.1, negatives, NaN, inf and junk strings; the
  ceiling boundary is inclusive; `above()` on a payload carrying the real USA 568 garbage row sets
  `alt_km=None`/`alt_suspect=True`/`el=None`, keeps the row, and sorts it last; `position()` flags the
  suspect altitude while preserving N2YO's elevation.
- Existing `test_hannibal_eme.py` (6 tests) still pass -- no regression.
- Render smoke-test: a two-row table (one good GEO, one suspect) prints the good row normally and the
  suspect row as `?  ?  ... [suspect TLE: altitude rejected]` with columns aligned.

### Not done / notes
- The guard is a **display/ingestion** safeguard, not a TLE re-fit: it does not try to recover a correct
  altitude for a bad element set, only to stop printing a false one. When N2YO later serves a sane
  `satalt` for the object (once its orbit is fit), it shows normally with no code change.
- `ALT_MAX_KM` is deliberately generous (0.5 Mm). If a genuine cislunar/deep-space object in a
  monitored category ever needs to show, raise the ceiling or special-case it; today nothing we track
  lives above it.

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
