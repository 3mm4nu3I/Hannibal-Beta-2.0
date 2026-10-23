"""Zombie check: which satellites on a list still transmit something an amateur station can hear.

    sources  SatNOGS DB       https://db.satnogs.org/api/satellites/   (full list, cached 24 h)
                              https://db.satnogs.org/api/transmitters/ (full list, cached 24 h)
             SatNOGS Network  https://network.satnogs.org/api/observations/ (vetted results, cached 1 h)
    auth     none; every call goes through hannibal_net (rate limited, cached, masked)

A position tells you where a satellite is, not whether anything on it still works. The overhead
list from N2YO looks the same for a live satellite and for one that died in 1966. This module
answers the second question with measured evidence, one tier at a time:

    NOT IN SATNOGS     no transmitter of this object is on record with the amateur network
    NO ACTIVE TX       on record, but no transmitter is marked active
    LISTED, NOT HEARD  an active transmitter is on record, but no vetted "good" result in the window
    HEARD              at least one vetted "good" SatNOGS observation in the window
    NOT CHECKED        the network could not be asked; the verdict becomes a lower bound

HEARD means a volunteer ground station saw that transmitter's signal (often only a carrier) or
decoded its telemetry. It says nothing about commanding the satellite. The UPLINK column shows
whether any transmitter on record has an uplink at all (type Transceiver or Transponder); a
relay needs one. Everything here is receive-only: nothing in this module transmits.

    python hannibal_zombie.py                          # the 148 military objects over Antwerp, 17 Oct 2026
    python hannibal_zombie.py --above                  # what N2YO lists as military overhead now (key needed)
    python hannibal_zombie.py --ids 2412,39483 --days 60 --json out.json
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_SATELLITES_URL = "https://db.satnogs.org/api/satellites/"
DB_TRANSMITTERS_URL = "https://db.satnogs.org/api/transmitters/"
NETWORK_OBS_URL = "https://network.satnogs.org/api/observations/"
DB_TTL = 24 * 3600
OBS_TTL = 3600
DEFAULT_DAYS = 30
PAGE = 25                 # SatNOGS Network page size: a full page means "at least this many"
MAX_DB_PAGES = 40         # only used if the DB ever starts paginating its lists
SEED_FILE = "zombie_targets_2026-10-17.json"
MILITARY = 30             # N2YO category id

HEARD, LISTED, NO_ACTIVE, NOT_IN_DB, UNCHECKED = (
    "HEARD", "LISTED, NOT HEARD", "NO ACTIVE TX", "NOT IN SATNOGS", "NOT CHECKED")
TIER_ORDER = [HEARD, LISTED, NO_ACTIVE, UNCHECKED, NOT_IN_DB]
UPLINK_TYPES = ("transceiver", "transponder")


# ------------------------------------------------------------------ targets ----
def _norad(value):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if 0 < n < 1_000_000 else None


def parse_ids(text):
    """'2412, 39483 25544' -> [2412, 39483, 25544] (order kept, duplicates dropped)."""
    out = []
    for token in re.split(r"[\s,;]+", str(text or "")):
        n = _norad(token)
        if n and n not in out:
            out.append(n)
    return out


def targets_from_json(data):
    """A list of {norad|id, name}, a list of ids, or norad_targets.json ({"targets": [...]})."""
    rows = data.get("targets", []) if isinstance(data, dict) else data
    out, seen = [], set()
    for entry in rows or []:
        if isinstance(entry, dict):
            n = _norad(entry.get("norad", entry.get("id", entry.get("norad_cat_id"))))
            name = str(entry.get("name") or "").strip()
        else:
            n, name = _norad(entry), ""
        if n and n not in seen:
            seen.add(n)
            out.append({"norad": n, "name": name})
    return out


def load_targets(path=None):
    """Targets from a JSON file or a plain list of ids. Default: the 17 Oct 2026 Antwerp export."""
    if path is None:
        from hannibal_net import resource_path
        path = resource_path(SEED_FILE)
    text = Path(path).read_text(encoding="utf-8")
    try:
        return targets_from_json(json.loads(text))
    except ValueError:
        return [{"norad": n, "name": ""} for n in parse_ids(text)]


def targets_from_n2yo(category=MILITARY):
    """What N2YO lists above the home location right now. Returns (targets, error)."""
    from hannibal_n2yo import N2YO
    res = N2YO().above(category)
    if not res.ok:
        return [], res.error
    return [{"norad": r["norad"], "name": r["name"]} for r in res.data["rows"] if r.get("norad")], ""


# ----------------------------------------------------------------- fetching ----
def _db_list(net, url):
    """One full SatNOGS DB list. Returns (items, error, note)."""
    res = net.get_json(url, params={"format": "json"}, ttl=DB_TTL, timeout=60)
    if not res.ok:
        return [], res.error, ""
    note = res.note if res.stale else ""
    if isinstance(res.data, list):
        return res.data, "", note
    if not isinstance(res.data, dict) or "results" not in res.data:
        return [], "unexpected SatNOGS DB response shape", note
    items, page = list(res.data.get("results") or []), res.data
    for _ in range(MAX_DB_PAGES):        # paginated form, in case the DB ever switches to it
        nxt = page.get("next")
        if not nxt:
            return items, "", note
        more = net.get_json(nxt, ttl=DB_TTL, timeout=60)
        if not more.ok or not isinstance(more.data, dict):
            return [], f"SatNOGS DB list incomplete ({more.error or 'bad page'})", note
        page = more.data
        items.extend(page.get("results") or [])
    return [], "SatNOGS DB list longer than the page cap", note


def index_db(satellites, transmitters):
    """-> ({norad: satellite}, {norad: [transmitters]})."""
    sats = {}
    for s in satellites or []:
        n = _norad(s.get("norad_cat_id")) if isinstance(s, dict) else None
        if n:
            sats[n] = s
    txs = {}
    for t in transmitters or []:
        n = _norad(t.get("norad_cat_id")) if isinstance(t, dict) else None
        if n:
            txs.setdefault(n, []).append(t)
    return sats, txs


def fetch_db(net):
    """Returns (sats_by_id, tx_by_id, error, note)."""
    sats, err1, note1 = _db_list(net, DB_SATELLITES_URL)
    txs, err2, note2 = _db_list(net, DB_TRANSMITTERS_URL)
    if err1 or err2:
        return {}, {}, err1 or err2, ""
    s, t = index_db(sats, txs)
    return s, t, "", note1 or note2


def window_start(days, now=None):
    """Start of the evidence window, rounded down to the hour so the hourly cache can hit."""
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).replace(minute=0, second=0, microsecond=0)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _when(text):
    try:
        return datetime.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_observations(net, norad, status, since):
    """Vetted observations of one object with one status since `since`. Returns (list or None, error)."""
    res = net.get_json(NETWORK_OBS_URL, params={"norad_cat_id": norad, "status": status,
                                                "start": _iso(since), "format": "json"},
                       ttl=OBS_TTL, timeout=30)
    if not res.ok:
        return None, res.error
    if not isinstance(res.data, list):
        return None, "unexpected SatNOGS Network response shape"
    return res.data, ""


def fetch_evidence(net, norad, since):
    good, err_g = fetch_observations(net, norad, "good", since)
    bad, err_b = fetch_observations(net, norad, "bad", since)
    return {"good": good, "bad": bad, "error": err_g or err_b}


# ----------------------------------------------------------------- analysis ----
def _kept(observations, status, norad, since):
    """Apply the filters locally as well, so a server that ignores one can't inflate a count."""
    out = []
    for o in observations or []:
        if not isinstance(o, dict) or str(o.get("status", "")).lower() != status:
            continue
        if _norad(o.get("norad_cat_id")) not in (None, norad):
            continue
        t = _when(o.get("end") or o.get("start"))
        if t is None or t < since:
            continue
        out.append(o)
    return sorted(out, key=lambda o: str(o.get("end") or o.get("start")), reverse=True)


def _mhz(hz):
    try:
        return f"{float(hz) / 1e6:.3f} MHz"
    except (TypeError, ValueError):
        return ""


def assess(target, sat, txs, evidence, since):
    norad = target["norad"]
    txs = txs or []
    active = [t for t in txs if str(t.get("status", "")).lower() == "active" and t.get("alive") is not False]
    row = {"norad": norad, "name": target.get("name") or (sat or {}).get("name") or "",
           "db_name": (sat or {}).get("name") or "", "in_satnogs": bool(sat or txs),
           "db_status": (sat or {}).get("status") or "", "launched": str((sat or {}).get("launched") or "")[:4],
           "transmitters": len(txs), "active_transmitters": len(active),
           "uplink_on_record": any(str(t.get("type", "")).lower() in UPLINK_TYPES for t in txs),
           "good": 0, "good_capped": False, "bad": 0, "bad_capped": False,
           "last_good": "", "heard_on": "", "station": "", "error": ""}
    if not row["in_satnogs"]:
        row["tier"] = NOT_IN_DB
        return row
    if evidence is None:          # nothing on record to listen for: SatNOGS schedules per transmitter
        row["tier"] = LISTED if active else NO_ACTIVE
        return row
    if evidence.get("error") or evidence.get("good") is None:
        row["tier"], row["error"] = UNCHECKED, evidence.get("error") or "no answer"
        return row
    good = _kept(evidence.get("good"), "good", norad, since)
    bad = _kept(evidence.get("bad"), "bad", norad, since)
    row.update(good=len(good), good_capped=len(evidence.get("good") or []) >= PAGE,
               bad=len(bad), bad_capped=len(evidence.get("bad") or []) >= PAGE)
    if good:
        g = good[0]
        row["last_good"] = str(g.get("end") or g.get("start"))[:16].replace("T", " ")
        row["heard_on"] = ", ".join(x for x in (g.get("transmitter_description"), g.get("transmitter_mode"),
                                                _mhz(g.get("transmitter_downlink_low"))) if x)
        row["station"] = str(g.get("station_name") or "")
        row["tier"] = HEARD
    else:
        row["tier"] = LISTED if active else NO_ACTIVE
    return row


def analyse(targets, sats, txs, evidence, days=DEFAULT_DAYS, since=None):
    """Pure: targets + indexed DB + {norad: evidence} -> result dict."""
    since = since or window_start(days)
    rows = [assess(t, sats.get(t["norad"]), txs.get(t["norad"]), evidence.get(t["norad"]), since) for t in targets]
    heard_rows = sorted((r for r in rows if r["tier"] == HEARD), key=lambda r: r["last_good"], reverse=True)
    rows = heard_rows + sorted((r for r in rows if r["tier"] != HEARD), key=lambda r: TIER_ORDER.index(r["tier"]))
    counts = Counter(r["tier"] for r in rows)
    heard = counts.get(HEARD, 0)
    unchecked = counts.get(UNCHECKED, 0)
    uplinks = sum(1 for r in rows if r["tier"] == HEARD and r["uplink_on_record"])
    verdict = f"HEARD in the last {days} days: {heard} of {len(rows)}"
    if unchecked:
        verdict += f" (at least; {unchecked} could not be checked)"
    return {"days": days, "since": _iso(since), "total": len(rows), "counts": {k: counts.get(k, 0) for k in TIER_ORDER},
            "heard": heard, "heard_with_uplink": uplinks, "unchecked": unchecked, "verdict": verdict, "rows": rows}


def run(targets, net=None, days=DEFAULT_DAYS, now=None):
    """Fetch and analyse. Returns (result, error)."""
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    if not targets:
        return None, "no targets"
    sats, txs, err, note = fetch_db(net)
    if err:
        return None, f"SatNOGS DB unavailable: {err}"
    since = window_start(days, now)
    evidence = {}
    for t in targets:
        n = t["norad"]
        if txs.get(n):           # only objects with a transmitter on record can have observations
            evidence[n] = fetch_evidence(net, n, since)
    result = analyse(targets, sats, txs, evidence, days, since)
    result["note"] = note
    return result, ""


# ------------------------------------------------------------------- report ----
def _count(n, capped):
    return f"{n}+" if capped else str(n)


def format_report(r, show_all=False):
    lines = [f"  ZOMBIE CHECK  {r['total']} targets, SatNOGS evidence since {r['since'].replace('T', ' ')[:16]} UTC "
             f"({r['days']} days)"]
    if r.get("note"):
        lines.append(f"  [!] {r['note']}")
    lines += ["", f"  {'NORAD':>6}  {'NAME':<24} {'LAUNCH':<6} {'TX(act)':<7} {'UPLINK':<6} {'GOOD':>4} {'BAD':>4}  "
                  f"{'LAST GOOD (UTC)':<16}  {'TIER / HEARD ON'}"]
    shown = [x for x in r["rows"] if show_all or x["tier"] != NOT_IN_DB]
    for x in shown:
        tail = x["tier"] + (f": {x['heard_on']} ({x['station']})" if x["tier"] == HEARD else "")
        if x["tier"] == UNCHECKED:
            tail += f": {x['error']}"
        tx = f"{x['transmitters']}({x['active_transmitters']})" if x["in_satnogs"] else "-"
        lines.append(f"  {x['norad']:>6}  {x['name'][:24]:<24} {x['launched'] or '-':<6} {tx:<7} "
                     f"{'yes' if x['uplink_on_record'] else 'no':<6} {_count(x['good'], x['good_capped']):>4} "
                     f"{_count(x['bad'], x['bad_capped']):>4}  {x['last_good'] or '-':<16}  {tail}")
    hidden = len(r["rows"]) - len(shown)
    if hidden:
        lines.append(f"  ... and {hidden} more NOT IN SATNOGS (no transmitter on record; --all lists them)")
    c = r["counts"]
    lines += ["", "  Tiers: " + " | ".join(f"{k} {c[k]}" for k in TIER_ORDER if c[k] or k in (HEARD, NOT_IN_DB)),
              "", f"  VERDICT: {r['verdict']}. With an uplink on record: {r['heard_with_uplink']} of those heard.",
              "  HEARD = a SatNOGS volunteer station saw this transmitter's signal (often just a carrier) in the window.",
              "  It is evidence of a working transmitter, not of a link anyone can command. A relay needs an uplink;",
              "  UPLINK says whether any transmitter on record has one. Positions alone (N2YO) can't tell live from dead."]
    return "\n".join(lines)


def report(targets=None, days=DEFAULT_DAYS, show_all=False, **kw):
    targets = load_targets() if targets is None else targets
    result, err = run(targets, days=days, **kw)
    return f"  [!] {err}" if err else format_report(result, show_all)


def screen_zombie(ask, print_fn, color=False):
    """[Z] screen for the Orbital Ops menu."""
    choice = ask("  Targets: [Enter] 148 military over Antwerp (17 Oct export), [A] military overhead now (N2YO),\n"
                 "           or NORAD ids separated by commas: ", "").strip()
    if choice.upper() == "A":
        targets, err = targets_from_n2yo()
        if err:
            print_fn(f"  [!] N2YO: {err}")
            return
    elif choice:
        targets = [{"norad": n, "name": ""} for n in parse_ids(choice)]
    else:
        targets = load_targets()
    try:
        days = max(1, min(365, int(ask(f"  Days of evidence [{DEFAULT_DAYS}]: ", str(DEFAULT_DAYS)) or DEFAULT_DAYS)))
    except ValueError:
        days = DEFAULT_DAYS
    print_fn(f"  Asking SatNOGS about {len(targets)} objects (database cached 24 h, observations 1 h)...")
    print_fn(report(targets, days=days))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Zombie check: which satellites still transmit something hearable (SatNOGS)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--ids", help="NORAD ids, comma separated")
    src.add_argument("--file", help="JSON or text file of targets (default: the 17 Oct 2026 Antwerp export)")
    src.add_argument("--above", action="store_true", help="military objects N2YO lists overhead now (N2YO key)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help="evidence window in days (default 30)")
    ap.add_argument("--all", action="store_true", help="also list every NOT IN SATNOGS target")
    ap.add_argument("--json", help="also write the result to this file")
    args = ap.parse_args(argv)
    try:
        import hannibal_security_bootstrap  # noqa: F401  (process-wide output masking)
    except Exception:  # noqa: BLE001
        pass
    if args.above:
        targets, err = targets_from_n2yo()
        if err:
            print(f"N2YO: {err}", file=sys.stderr)
            return 1
    elif args.ids:
        targets = [{"norad": n, "name": ""} for n in parse_ids(args.ids)]
    else:
        targets = load_targets(args.file)
    result, err = run(targets, days=max(1, args.days))
    if err:
        print(err, file=sys.stderr)
        return 1
    print(format_report(result, args.all))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    return 2 if result["unchecked"] else 0


if __name__ == "__main__":
    sys.exit(main())
