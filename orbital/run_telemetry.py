"""Hannibal orbital telemetry engine.

One engine, two ways to use it:

  * standalone:   python run_telemetry.py        (prints a table, writes telemetry_report.json)
  * imported:     import run_telemetry           (hannibal_terminal.py's [L] view does this)

Importing this module has NO side effects: it does not install packages, wrap
stdout, or touch the network. All of that happens only inside main().

Data sources
  * SatNOGS Network  - recent ground-station observations -> "packet health"
  * Space-Track      - latest TLE epoch (optional; needs a free account; rate-limit safe + cached)

Space-Track credentials come from the SPACETRACK_USER / SPACETRACK_PASS
environment variables first, then from norad_targets.json (unless the file
still holds the YOUR_... placeholders).
"""
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # shared redaction primitives; degrade to pass-through if the file is missing
    from secret_masking import redact, redact_text
except ImportError:  # pragma: no cover
    def redact_text(value):
        return str(value)

    def redact(value):
        return value

FROZEN = getattr(sys, "frozen", False)
TARGETS_FILE = "norad_targets.json"
REPORT_FILE = "telemetry_report.json"
SATNOGS_URL = "https://network.satnogs.org/api/observations/"
HEADERS = {"User-Agent": "Hannibal-Telemetry/2.0"}
MAX_PAGES = 6          # SatNOGS pages are small (25); cap so one satellite can't stall a scan
HTTP_TIMEOUT = 15

# Link-health evidence gate (patch_telemetry 2026-10-11). See classify().
MIN_SAMPLE = 8          # vetted observations needed before a verdict is issued
ONLINE_PCT = 0.75       # point estimate needed for ONLINE ...
OFFLINE_PCT = 0.25      # ... and below this for OFFLINE
CONFIDENT = 0.50        # the 95% interval must sit on the right side of 50%
WILSON_Z = 1.96         # 95% two-sided
STALE_TLE_DAYS = 14     # older element sets are flagged; SGP4 error grows with age
_TRUNCATED = set()      # NORAD ids whose last fetch hit MAX_PAGES

# Bad-connection handling (patch_telemetry 1.2.0). See _get() and scan().
# HANNIBAL_NET_PROFILE=low (set by HANNIBAL_LOW_INTERNET.bat) trades speed for surviving a bad link
# and downloads less; anything else is the normal profile.
LOW_NET = os.getenv("HANNIBAL_NET_PROFILE", "normal").strip().lower() == "low"
CONNECT_TIMEOUT = 20 if LOW_NET else 10     # seconds to open the connection ...
READ_TIMEOUT = 60 if LOW_NET else 30        # ... and to wait for the next chunk of JSON
RETRIES = 3 if LOW_NET else 2               # extra attempts after a timeout, drop, 429 or 5xx
BACKOFF = (5, 15, 30) if LOW_NET else (3, 8)  # seconds before each retry
OFFLINE_AFTER = 1 if LOW_NET else 2         # network failures in a row before the rest is skipped
if LOW_NET:
    MAX_PAGES = 2       # 50 observations per satellite instead of 150; busy ones get flagged Truncated
_NETWORK_FAIL = set()   # NORAD ids whose last fetch died at the network level

# Verified in-orbit on 2026-10-01 against the SatNOGS DB. Used only when
# norad_targets.json is missing or unreadable.
DEFAULT_FLEET = [
    {"id": 25544, "name": "ISS (ZARYA)", "type": "Amateur Radio / Habited"},
    {"id": 39444, "name": "FUNcube-1 (AO-73)", "type": "Amateur Radio / Education"},
    {"id": 39161, "name": "ESTCube-1", "type": "Educational / Estonian CubeSat"},
    {"id": 40931, "name": "LAPAN-A2 (ORARI / IO-86)", "type": "Amateur Radio / Equatorial"},
    {"id": 40069, "name": "METEOR M-2", "type": "Weather / LRPT"},
    {"id": 7530, "name": "OSCAR 7 (AO-7)", "type": "Amateur Radio / Linear Transponder"},
    {"id": 24278, "name": "JAS-2 (FO-29)", "type": "Amateur Radio / Linear Transponder"},
]


# ---------------------------------------------------------------- paths ----
from hannibal_net import base_dir, resource_path  # noqa: E402  (single definition shared by every module)


def report_path():
    return base_dir() / REPORT_FILE


# --------------------------------------------------------------- config ----
def load_config():
    cfg = {"satnogs": {"lookback_hours": 24}, "targets": list(DEFAULT_FLEET), "space_track_auth": {}}
    path = resource_path(TARGETS_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as exc:
        print(f"[!] Could not read {path.name}: {redact_text(exc)} -- using built-in fleet.")
        return cfg

    targets = []
    for entry in data.get("targets", []) if isinstance(data, dict) else []:
        try:
            targets.append({"id": int(entry["id"]), "name": str(entry["name"]),
                            "type": str(entry.get("type", ""))})
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed rows instead of crashing the scan
    if targets:
        cfg["targets"] = targets
    try:
        hours = float(data.get("satnogs", {}).get("lookback_hours", 24))
        if hours > 0:
            cfg["satnogs"]["lookback_hours"] = hours
    except (TypeError, ValueError):
        pass
    auth = data.get("space_track_auth")
    if isinstance(auth, dict):
        cfg["space_track_auth"] = auth
    return cfg


def get_credentials(cfg):
    """env vars, then credentials typed at start-up, then norad_targets.json (placeholders ignored)."""
    from hannibal_spacetrack import get_credentials as _creds
    return _creds(cfg.get("space_track_auth", {}))


# -------------------------------------------------------------- fetching ----
def _requests():
    import requests  # imported lazily so merely importing this module can never fail
    return requests


def fetch_satnogs(session, norad_id, hours_back):
    """Return (observations, error). `error` is None on success.

    A network/API failure returns ([], "message") so it can be told apart from
    a satellite that genuinely had no passes.
    """
    requests = _requests()
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    params = {
        "norad_cat_id": norad_id,
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": "json",
    }
    url, observations = SATNOGS_URL, []
    _TRUNCATED.discard(norad_id)
    _NETWORK_FAIL.discard(norad_id)
    try:
        for _ in range(MAX_PAGES):
            res = _get(session, url, params)
            page = res.json()
            if not isinstance(page, list):
                return [], "unexpected SatNOGS response shape"
            observations.extend(page)
            nxt = res.links.get("next", {}).get("url")
            if not nxt:
                break
            url, params = nxt, None  # the next-link already carries the query string
        else:
            # Loop ran out with a next-link still pending: the window is partial.
            _TRUNCATED.add(norad_id)
        return observations, None
    except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
        _NETWORK_FAIL.add(norad_id)   # the link, not SatNOGS: feeds the offline short-cut in scan()
        return observations, redact_text(exc)
    except (requests.RequestException, ValueError) as exc:
        return observations, redact_text(exc)


def _retry_after(res):
    try:
        return max(0.0, float(res.headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        return None


def _get(session, url, params):
    """GET that survives a bad connection: split timeouts, RETRIES extra attempts with BACKOFF.

    Retries timeouts, dropped connections (including a body cut off half-way) and
    429/5xx answers. Anything else (404, bad request) fails at once. Raises the
    last error when every attempt fails, so fetch_satnogs() reports it as before.
    """
    requests = _requests()
    transient = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)
    for attempt in range(RETRIES + 1):
        wait = BACKOFF[min(attempt, len(BACKOFF) - 1)]
        try:
            res = session.get(url, params=params, headers=HEADERS, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            if res.status_code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                time.sleep(min(_retry_after(res) or wait, 30))
                continue
            res.raise_for_status()
            return res
        except transient:
            if attempt >= RETRIES:
                raise
            time.sleep(wait)


def fetch_spacetrack_epochs(session, user, password, norad_ids):
    """Return (epochs, error, note).

    Goes through hannibal_spacetrack, which enforces Space-Track's published limits
    (GP: one live query per hour, <30 req/min, <300 req/h) and serves cached element
    sets in between. `session` is accepted for backwards compatibility and unused: the
    shared hannibal_net layer owns the connection. `note` says when cached data was used.
    """
    from hannibal_spacetrack import SpaceTrack
    client = SpaceTrack(user=user, password=password)
    epochs, info = client.gp_epochs(norad_ids)
    if not epochs and info:
        return {}, redact_text(info), ""
    return epochs, None, info or ""


# ---------------------------------------------------------- classification ----
def wilson(k, n, z=WILSON_Z):
    """95% Wilson score interval for k successes in n trials -> (low, high).

    Used instead of the plain +/- interval because it stays inside [0, 1] and
    behaves at 0/n and n/n, which is exactly where small satellite samples sit.
    """
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(observations):
    """SatNOGS `status` is lowercase: good / bad / failed / unknown / future.

    good   = signal decoded            -> counts for the satellite
    bad    = listened, nothing heard   -> counts against the satellite
    failed = the STATION broke (no audio/waterfall uploaded) -> says nothing
             about the satellite, reported separately as Station Failures
    unknown = awaiting vetting, future = scheduled; neither is counted.
    Returns (good, bad, failed, unvetted).
    """
    states = [str(o.get("status", "")).lower() for o in observations]
    return (states.count("good"), states.count("bad"),
            states.count("failed"), states.count("unknown"))


def classify(good, bad, failed=0, unvetted=0):
    """Evidence-gated verdict. Thin samples get LOW SAMPLE, not a verdict.

    ONLINE        p >= 75%  and 95% lower bound >= 50%
    OFFLINE       p <  25%  and 95% upper bound <  50%
    INTERMITTENT  anything in between, or a confident-looking % the interval can't back
    LOW SAMPLE    fewer than MIN_SAMPLE vetted observations
    """
    n = good + bad
    if n == 0:
        if unvetted:
            return "UNVETTED"
        return "STATION FAULT" if failed else "NO PASSES"
    if n < MIN_SAMPLE:
        return "LOW SAMPLE"
    p = good / n
    low, high = wilson(good, n)
    if p >= ONLINE_PCT and low >= CONFIDENT:
        return "ONLINE"
    if p < OFFLINE_PCT and high < CONFIDENT:
        return "OFFLINE"
    return "INTERMITTENT"


def health_text(good, bad):
    """'78% 64/82 [68-86]' -> share, counts, 95% range. Whole percent so it fits the 20-wide column."""
    n = good + bad
    if n == 0:
        return "N/A (0 obs)"
    low, high = wilson(good, n)
    return f"{good / n * 100:.0f}% {good}/{n} [{low * 100:.0f}-{high * 100:.0f}]"


def tle_age_days(raw, now=None):
    """Days since a Space-Track EPOCH string ('2026-10-03T11:57:00.000000'); None if unparseable."""
    if not raw:
        return None
    try:
        epoch = datetime.fromisoformat(str(raw).split(".")[0].replace(" ", "T"))
    except ValueError:
        return None
    if epoch.tzinfo is None:
        epoch = epoch.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (now - epoch).total_seconds() / 86400.0


def format_epoch(raw):
    return raw.split(".")[0].replace("T", " ") if raw else "N/A"


# --------------------------------------------------------------------- scan ----
def scan(progress=None):
    """Run a full scan. Returns (rows, meta).

    rows: list of dicts in the telemetry_report.json schema (what the dashboard reads).
    meta: {"errors": int, "spacetrack": str, "hours": float}
    progress: optional callable(done_count, total, row).
    """
    requests = _requests()
    cfg = load_config()
    targets = cfg["targets"]
    hours = cfg["satnogs"]["lookback_hours"]
    user, password = get_credentials(cfg)

    rows, errors = [], 0
    dead_streak = 0
    try:   # last known results, used for any satellite this scan can't reach
        previous = {r.get("NORAD ID"): r for r in load_cached_report()[0]
                    if isinstance(r, dict) and r.get("Status") != "LINK ERROR"}
    except Exception:  # noqa: BLE001 - a bad cache must never stop a scan
        previous = {}
    with requests.Session() as session:
        if user:
            epochs, st_err, st_note = fetch_spacetrack_epochs(session, user, password, [t["id"] for t in targets])
            st_state = "ok" if st_err is None else st_err
        else:
            epochs, st_state, st_note = {}, "no credentials", ""

        for index, target in enumerate(targets, 1):
            if dead_streak >= OFFLINE_AFTER:
                observations, err = [], "skipped: connection looks down"
            else:
                observations, err = fetch_satnogs(session, target["id"], hours)
                dead_streak = dead_streak + 1 if target["id"] in _NETWORK_FAIL else 0
            good, bad, failed, unvetted = summarize(observations)
            from_cache = False
            if err:
                errors += 1
                old = previous.get(target["id"])
                if old:   # keep the last known result, marked *, rather than a blank LINK ERROR
                    status = old.get("Status", "LINK ERROR")
                    health = str(old.get("Packet Health", "")).rstrip("*") + "*"
                    failed = old.get("Station Failures", 0)
                    from_cache = True
                else:
                    status, health = "LINK ERROR", "N/A (fetch failed)"
            else:
                status = classify(good, bad, failed, unvetted)
                health = health_text(good, bad)
            raw_epoch = epochs.get(target["id"])
            if raw_epoch:
                epoch = format_epoch(raw_epoch)
            else:
                epoch = "N/A (No Auth)" if st_state == "no credentials" else "N/A"
            age = tle_age_days(raw_epoch)
            row = {"NORAD ID": target["id"], "Target Name": target["name"], "TLE Epoch": epoch,
                   "Status": status, "Packet Health": health,
                   "Station Failures": failed,
                   "TLE Age Days": round(age, 1) if age is not None else None,
                   "TLE Stale": bool(age is not None and age > STALE_TLE_DAYS),
                   "Truncated": target["id"] in _TRUNCATED,
                   "From Cache": from_cache}
            rows.append(row)
            if progress:
                progress(index, len(targets), row)
    return rows, {"errors": errors, "spacetrack": st_state, "spacetrack_note": st_note, "hours": hours}


# ------------------------------------------------------------------- report ----
def write_report(rows, meta=None):
    """Atomically write telemetry_report.json. Returns True if written.

    If EVERY satellite failed to fetch (offline machine, SatNOGS down), the
    previous report is kept instead of being overwritten with error rows.
    """
    if rows and meta and meta.get("errors", 0) >= len(rows):
        return False
    path = report_path()
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(redact(rows), fh, indent=2)
    os.replace(tmp, path)
    return True


def load_cached_report():
    """Return (rows, age_seconds). ([], None) if there is no readable report."""
    path = report_path()
    try:
        age = max(0.0, time.time() - path.stat().st_mtime)
        with open(path, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
        return (rows if isinstance(rows, list) else []), age
    except (OSError, ValueError):
        return [], None


def format_table(rows):
    cols = ["NORAD ID", "Target Name", "TLE Epoch", "Status", "Packet Health"]
    cells = [[str(r.get(c, "")) for c in cols] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) if cells else len(c) for i, c in enumerate(cols)]
    line = lambda vals: " | ".join(v.ljust(w) for v, w in zip(vals, widths))
    out = [line(cols), "-+-".join("-" * w for w in widths)]
    out += [line(row) for row in cells]
    return "\n".join(out)


# --------------------------------------------------------------------- CLI ----
def ensure_dependencies():
    """Auto-install `requests` -- only when running from source, never from a frozen .exe
    (where sys.executable is the app itself and 'pip' would relaunch it)."""
    if FROZEN:
        return
    try:
        import requests  # noqa: F401
    except ImportError:
        print("[*] Auto-installing missing package: requests ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "--quiet"])


def main():
    ensure_dependencies()
    try:  # process-wide output redaction for standalone runs
        import hannibal_security_bootstrap  # noqa: F401
    except ImportError:
        pass

    print("[*] Hannibal Telemetry Engine Online (redaction active).")
    cfg = load_config()
    print(f"[*] Scanning {len(cfg['targets'])} targets over a {cfg['satnogs']['lookback_hours']:g}h window...\n")
    rows, meta = scan(progress=lambda i, n, r: print(f"    [{i}/{n}] {r['Target Name']}: {r['Status']}"))
    print("\n" + format_table(rows) + "\n")
    note = f" ({meta['spacetrack_note']})" if meta.get("spacetrack_note") else ""
    print(f"[*] Space-Track: {meta['spacetrack']}{note}")
    if write_report(rows, meta):
        print(f"[+] Sanitized telemetry report written to {report_path()}")
        return 0
    print("[!] Every SatNOGS request failed (offline?). Existing report left untouched.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
