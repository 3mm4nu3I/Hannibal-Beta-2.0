# PROJECT HANNIBAL // ORBITAL DIRECTORATE

```
                           /\
                          /  \
                         /    \
            ____________/      \____________
            \                              /
              \       PROJECT  HANNIBAL  /
                \ ORBITAL  DIRECTORATE /
                /                      \
               /         ______         \
              /       .-'      '-.       \
             /     .-'            '-.     \
            /   .-'                  '-.   \
           /_.-'                        '-._\

            ОРБИТАЛЬНОЕ УПРАВЛЕНИЕ  *  VPERED, K ZVEZDAM!
```

## New on 2026-10-11

| Key | What | Who |
|---|---|---|
| `HANNIBAL_NORMAL.bat` / `HANNIBAL_LOW_INTERNET.bat` | start with the normal or the bad-connection network profile | everyone |
| `[D]` Debris cascade (new 2026-10-22) | Kessler watch from the public CelesTrak catalog: objects per 50 km shell, drag cleanup time, cascade index. No key. `python hannibal_kessler.py` | everyone |
| `[1]` Fleet telemetry | evidence-gated link health: LOW SAMPLE under 8 observations, 95% ranges, stale TLE in red, `*` = last known value | everyone |
| `[M]` Macro (FRED) | CPI, core PCE, rates, curve, M2 velocity, Brent, dollar. Key: `python hannibal_fred.py --set-key` | everyone |
| `[R]` Market brain [DEV] | what the market is thinking: ten lobes, live transmission paths, in your browser (127.0.0.1 only) | developers |
| `[T]` Happiness theorem [DEV] | the Grand Unified Happiness Theorem & 10-lobe cranial report (also a card on the [R] page) | developers |

Developers: set the developer key once with `python hannibal_brain.py --set-dev-key`. Your personal profile goes in
`brain_profile.json` next to the scripts (private, git-ignored); `brain_profile.example.json` shows the shape.
Full detail: [CHANGELOG.md](CHANGELOG.md), [CHANGELOG_telemetry.md](CHANGELOG_telemetry.md), [../ROADMAP.md](../ROADMAP.md).

One module set that runs **standalone** or **inside `hannibal_terminal.py`**, and sends every API
call through the same masking layer you already use.

```
python hannibal_orbital.py          # interactive menu (standalone)
python patch_hannibal.py            # wire the keys below into hannibal_terminal.py
```

## Where do I type my passwords?

When the Orbital Ops menu opens (`python hannibal_orbital.py`, or `[V]` in the terminal) it asks **once**:

```
SPACE-TRACK LOGIN ...        Username (your e-mail):        <- visible
                             Password (hidden as you type): <- nothing is shown while you type
N2YO API KEY ...             API key (hidden as you type):
```

* Press **Enter** at any prompt to skip that service. You are not asked again until you pick **`[K]` Logins & keys**.
* What you type is hidden, **kept in memory** for the run, and registered with the masker so it is scrubbed from anything
  printed or logged.
* The login is checked right away. A wrong Space-Track password is retried (3 tries); if the service cannot be reached the
  login is kept for the session with a note.
* After a login is accepted you are asked **"Remember it on this computer? [y/N]"**. Only on `y` is anything stored:
  in the operating-system credential store if the optional `keyring` package is installed (Windows Credential Manager),
  otherwise in a plain-text file in **your own user folder** (`~/.hannibal/credentials.json`, owner-only permissions). Saved
  logins are loaded silently next time. `[K]` offers to forget them again.
* Optional: put `hannibal_credentials.local.json` next to the program to pre-load a login
  (`{"spacetrack_user": "...", "spacetrack_pass": "...", "n2yo_key": "..."}`). Keep that file private and out of any zip you share.
* Order of precedence: environment variables, then what you typed this run, then saved, then the local file.
  Windows: `setx SPACETRACK_USER you@mail.com`, `setx SPACETRACK_PASS ...`, `setx N2YO_API_KEY ...`, open a new terminal.
* The N2YO key is the free **REST** API key from your n2yo.com profile (the SOAP key does not work).

## What it does

| Source | What you get | Key needed |
|---|---|---|
| SatNOGS Network | link health of your satellites (`norad_targets.json`) | none |
| Space-Track | re-entry watch (DECAY + TIP), public close approaches (CDM), box score by country, TLE epochs | free account |
| NASA/JPL Horizons | Sun, Moon, planets over your home; ephemeris/vectors for any body | none |
| N2YO REST API | **main window**: Military and Globalstar satellites above you right now; lookup of any satellite (position, TLE, visual and radio passes); the same lists on the 3D globe | free N2YO API key |
| NASA/JPL small-body | browser of **all 536 known asteroid/comet/TNO moons** (`sb_sat`: filter by class, name or number, physical parameters); radar delay/Doppler astrometry (`sb_radar`) | none |
| NASA/JPL periodic orbits | three-body families: halo, DRO, Lyapunov, ... | none |
| satellitemap.space BlueGlobe | 3D globe dashboard, passes, in-my-sky, POV rides | `BLUEGLOBE_API_KEY` (test key built in) |
| satellitemap.space feed | optional ADS-B feeder (uploads **your** receiver data; off by default) | your own receiver |

USSR / Russian Federation objects (Space-Track code `CIS`) are highlighted red in the re-entry and
box-score screens. Soviet space art lives in `hannibal_art.py` (menu `[A]`, or `--art`).

## Terminal keys (after `patch_hannibal.py`)

* `[L]` fleet link health (press again to force a rescan)
* `[B]` open the 3D BlueGlobe dashboard
* `[V]` Orbital Ops page; press `[V]` again to open the menu (asks for your logins once, then shows Military + Globalstar overhead)

## The Orbital Ops menu

```
[H] Home window    Military + Globalstar satellites above you now (also shown automatically when the menu opens)
[N] N2YO satellites  Military / Globalstar / any other category / a NORAD id / your fleet -> detail screen
                     (position now, TLE, next visual and radio passes) and [G] to show it on the 3D globe
[7] Asteroid moons   every body with moons; class code, name or number; paged list; detail with the moon table
[K] Logins & keys    type or change the Space-Track password and the N2YO key
[I] Breach log        probe/attack IPs (geolocated), phone metadata, compliance record
```

The BlueGlobe dashboard has an **ABOVE NOW** panel (click a row to fly to the satellite; buttons load the military or
Globalstar satellites on the globe, and both are loaded at start-up), an **ASTEROID MOONS** panel, a **BREACH LOG** panel,
and N2YO data in the target HUD. `http://localhost:8080/blueglobe_dashboard.html?norad=25544,39444` loads specific
satellites (digits only, at most 50).

## [I] Breach log -- IP geolocation + phone metadata, for incident write-ups

What it's for: when something probes or breaches your stuff, you need a record of what happened and enough to start an
investigation (an attacker's rough location, whether a phone number that showed up is a real mobile line or a VOIP/burner).
That's what this is. What it deliberately is **not**: a way to resolve an arbitrary phone number to a person's live
location. That capability only exists through a carrier's own lawful-intercept process -- it is not something a local
script can provide, so there's no code path here for it, regardless of what calls it.

How it works:

* The BlueGlobe server (`hannibal_blueglobe.py`) automatically logs any request that fails the Host-header guard or hits
  an unknown route -- source IP, what it tried, when. Repeats from the same IP/kind within 60 s bump a counter instead of
  flooding the log.
* `hannibal_geoint.record_attempt(ip, kind, detail, phone=...)` is the one way anything enters the log -- call it from
  anywhere else you want to feed in (a login form, a dev page, a report of a suspicious call/SMS), or use menu **[I] -> [M]**
  to add one by hand.
* **Lookups only work on an IP or phone number that is already in the log.** `lookup_ip()` and `phone_metadata()` both
  refuse anything that hasn't been logged first -- so this can't be used as a general-purpose lookup tool on third
  parties, only to enrich an event your own system (or you, by hand) actually recorded.
* IP geolocation uses `ipapi.co` (free, no key, masked/cached/throttled like every other call here; private/loopback/
  reserved addresses are recognised locally and never sent anywhere). Phone metadata is parsed entirely offline by the
  `phonenumbers` library -- country, the number's registered range/region, carrier, line type (mobile / VOIP / fixed /
  toll-free / etc.) -- no network call, no location.
* `hannibal_breach_log.jsonl` (next to the program) is set read-only (0o400 / the Windows read-only attribute) between
  writes, so a stray edit from outside the app needs a deliberate permission change first. This deters casual tampering
  with the compliance record; it is not a defence against someone with full control of the machine, and that limit is
  worth keeping in mind rather than assuming it's stronger than it is.

## Standalone

```
python hannibal_orbital.py            menu
python hannibal_orbital.py --home     one-shot screens: --home --sat 25544 --moons --scan --sky --decay
                                      --conjunctions --boxscore --art --status --dashboard --feeder
python hannibal_orbital.py --no-login never ask for the Space-Track / N2YO login
```

`run_standalone.bat` does the same on Windows.

## Patching the main terminal

`patch_hannibal.py` edits your `hannibal_terminal.py` in place, with a backup
(`hannibal_terminal.py.pre-orbital.bak`). It is all-or-nothing, safe to run twice, handles CRLF/BOM files,
and can undo itself:

```
python patch_hannibal.py --dry-run     show what would change
python patch_hannibal.py --status      what is already applied
python patch_hannibal.py --revert      restore the backup
python patch_hannibal.py --no-fixes    skip the four host-bug fixes (below)
```

The shipped `hannibal_terminal.py` is already patched. `integrate_hannibal.bat` / `patch2.sh` copy the
modules into your Hannibal folder and run the patcher on *your* terminal file instead.

The patch also fixes bugs in the terminal itself that stopped it from running:
`audit_event()` used `datetime.now(timezone.utc)` on the module (AttributeError at login),
`sanitize_terminal_text`, `log_to_db` and `log_insider_to_db` were called but never defined, and the lowercase
`r/a/j/e/n` hotkeys never matched the uppercase market keys.

## Masking

* Standalone: `hannibal_orbital.py` imports `hannibal_security_bootstrap`, which wraps stdout/stderr and
  logging with `secret_masking`.
* Inside the terminal: the patch imports the same bootstrap.
* Always: `hannibal_net.py` redacts URLs, parameters and exception text, and redacts cached payloads. Credentials
  travel only in the Space-Track login POST body (the N2YO key only as the `apiKey` query parameter, which is
  stripped from every URL, error and cache file); they are never in a log, cache file or screen.
* `HANNIBAL_NO_MASK=1` turns the wrapper off.
* Known false positive: the masker hides the word after "token" (a headline "token unlock" prints as
  "token ************").

## Rate limits (enforced for you)

Space-Track policy is under 30 requests/minute and 300/hour, GP (TLEs) once an hour, SATCAT/DECAY/BOXSCORE
once a day, CDM 3 times a day, and comma-separated id lists instead of many queries. `hannibal_net.py` caches per
those frequencies (in `hannibal_cache/`), limits to 25/min and 250/h, and serves a stale cached copy if a live call
fails. JPL calls are spaced 1 s apart; the feeder never goes faster than the documented 2 s. N2YO allows 100 requests
per hour for passes and "above" and 1000 for TLE and positions: results are cached (above 5 min, TLE 6 h, passes 30 min)
and the client refuses to go past 90 / 900 per hour. IP geolocation (`ipapi.co`) is capped at 500/h locally, well under
its free-tier daily limit, and each IP is cached for 7 days since geography for a given address barely changes.

## Configuration (environment variables)

```
SPACETRACK_USER / SPACETRACK_PASS      preferred over what you type and over norad_targets.json
N2YO_API_KEY                           your N2YO REST key (same precedence)
BLUEGLOBE_API_KEY                      your BlueGlobe key (your origin must be whitelisted)
HANNIBAL_HOME_LAT / _LON / _ALT_KM / _NAME     your sky location (no default location in source: set these, or sky features compute from 0, 0)
HANNIBAL_ADSB_SOURCE / HANNIBAL_FEEDER_ID      feeder source URL / feeder id
HANNIBAL_ASCII_ONLY=1                  pure ASCII art for consoles without block glyphs
HANNIBAL_NO_MASK=1  HANNIBAL_NO_ANIM=1
```

## Files

```
hannibal_orbital.py     the app: menu, CLI, providers, terminal glue
hannibal_net.py         shared HTTP layer: masking, cache, throttle, retries
hannibal_spacetrack.py  Space-Track client        hannibal_nasa.py   Horizons, sb_sat, sb_radar, periodic_orbits
hannibal_n2yo.py        N2YO REST client          hannibal_login.py  start-up prompts (hidden, memory only)
hannibal_creds.py       credential lookup        hannibal_vault.py  optional "remember me" store
hannibal_feeder.py      optional ADS-B feeder     hannibal_art.py    Soviet space ASCII art
hannibal_geoint.py      breach log, IP geolocation, offline phone metadata (menu [I])
run_telemetry.py        SatNOGS engine            hannibal_blueglobe.py + blueglobe_dashboard.html  3D dashboard
patch_hannibal.py       terminal patcher          secret_masking.py, hannibal_security_bootstrap.py, sitecustomize.py
norad_targets.json      your fleet (edit freely)  hannibal_terminal.spec, build.bat   Windows .exe build
```

## Verified vs. not verified

Verified against live services from the build sandbox: JPL Horizons (observer table and its column names),
`sb_sat` (the full 536-moon listing the browser is built on), `sb_radar`, `periodic_orbits`, and a full SatNOGS scan.
Several hundred offline checks cover the rest, including a pseudo-terminal run that types a password and a key at the start-up
prompt and checks that neither is echoed, printed or written to disk.

Verified live as well (with a real Space-Track login and N2YO key): the Space-Track login and the DECAY, TIP, BOXSCORE and
GP and CDM responses, and every N2YO endpoint used here (TLE, positions, visual passes, radio passes, above for Military and
Globalstar). Requests are cached and throttled, so this costs a handful of calls.

Also verified live: the CDM (close approaches) query. Not verified live:

* The BlueGlobe dashboard was tested in headless Chromium against a stand-in library; the real `blueglobe.js` needs your
  API key and a whitelisted origin. The ADS-B feeder was tested against a stand-in server only. The `.exe` build needs
  Windows (`build.bat`).
