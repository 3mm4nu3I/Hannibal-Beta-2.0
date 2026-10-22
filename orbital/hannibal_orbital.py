"""PROJECT HANNIBAL // ORBITAL DIRECTORATE

One module, three ways to use it:

  python hannibal_orbital.py              interactive menu (standalone)
  python hannibal_orbital.py --sky        one-shot screens: --scan --sky --decay --boxscore
                                          --conjunctions --status --dashboard --feeder
  import hannibal_orbital as sat_ops      the main terminal's [L] / [B] / [V] keys call into this
                                          (patch_hannibal.py wires that up for you)

Data sources
  SatNOGS Network   link health of amateur / educational satellites          (run_telemetry.py)
  Space-Track       re-entries (DECAY, TIP), conjunctions, catalogue box score, TLE epochs
  NASA/JPL          Horizons sky positions + ephemerides, small-body moons, radar astrometry,
                    three-body periodic orbits
  satellitemap.space  BlueGlobe 3D globe (hannibal_blueglobe.py) and the optional ADS-B feeder

Masking: every request goes through hannibal_net (URLs, parameters and errors are redacted,
cached copies are redacted, credentials never reach disk or a log), and the standalone entry
point installs the process-wide stdout/stderr/logging redaction from
hannibal_security_bootstrap before it does anything else.
"""
import argparse
import getpass
import os
import sys
import threading
import time

import hannibal_art as art
import hannibal_feeder
import hannibal_geoint
import hannibal_login
import hannibal_n2yo
import run_telemetry as rt
from hannibal_creds import session_get, session_set
from hannibal_net import base_dir, default_net, home_location, mask_id, redact_text
from hannibal_n2yo import CATEGORIES, GLOBALSTAR, MENU_CATEGORIES, MILITARY, N2YO
from hannibal_nasa import FAMILIES, Nasa
from hannibal_spacetrack import CREDENTIALS_HELP, SpaceTrack, get_credentials

SOVIET_CODES = {"CIS", "USSR", "SU", "RU", "RUS"}


def is_soviet(*values):
    """True for the USSR / Russian Federation (Space-Track uses 'CIS' for the Soviet-era block)."""
    for v in values:
        t = str(v or "").upper().strip()
        if t in SOVIET_CODES or "SOVIET" in t or "RUSSIA" in t or "COMMONWEALTH OF INDEPENDENT" in t:
            return True
    return False


def _i(v, default=0):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _f(v, default=None):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


# ================================================================ providers ====
# Plain functions returning plain dicts: used by the menu, the CLI, the terminal and the
# dashboard server alike. Each is safe to call repeatedly -- hannibal_net caches per the
# providers' published pull-frequency policies -- and never raises.
_lock = threading.Lock()
_clients = {}


def _client(name, factory):
    """Cached client. One that has no login yet is rebuilt on each call, so a password typed later (menu [K]) is picked up
    even by the dashboard server's own copy of this module."""
    with _lock:
        c = _clients.get(name)
        if c is None or not getattr(c, "configured", True):
            c = _clients[name] = factory()
        return c


def spacetrack():
    return _client("st", SpaceTrack)


def nasa():
    with _lock:
        if "nasa" not in _clients:
            _clients["nasa"] = Nasa()
        return _clients["nasa"]


def n2yo():
    return _client("n2yo", N2YO)


def reset_clients():
    with _lock:
        _clients.clear()


def _st_result(res):
    return {"error": res.error, "note": res.note, "stale": res.stale, "cached": res.cached,
            "age": res.age, "rows": []}


def get_sky():
    home = home_location()
    try:
        rows, errors = nasa().horizons.sky_now()
    except Exception as exc:  # never let a provider take down a UI
        return {"home": home, "as_of": "", "rows": [], "errors": [redact_text(exc)]}
    for r in rows:
        r["dir"] = art.compass(r["az"])
    return {"home": home, "as_of": rows[0]["as_of"] if rows else "", "rows": rows, "errors": errors}


def get_decay(limit=25):
    try:
        res = spacetrack().decay(limit)
    except Exception as exc:
        return {"error": redact_text(exc), "note": "", "rows": []}
    out = _st_result(res)
    if res.data:
        out["rows"] = [{
            "norad": _i(r.get("NORAD_CAT_ID")), "name": r.get("OBJECT_NAME") or "UNKNOWN",
            "country": r.get("COUNTRY") or "", "decay_epoch": r.get("DECAY_EPOCH") or "",
            "msg_type": r.get("MSG_TYPE") or "", "rcs": r.get("RCS_SIZE") or "",
            "soviet": is_soviet(r.get("COUNTRY")),
        } for r in res.data]
    return out


def _wrap_lon(lon):
    """Space-Track TIP longitudes run 0..360 east; show -180..180."""
    return None if lon is None else (lon - 360.0 if lon > 180.0 else lon)


def get_tip(limit=10):
    try:
        res = spacetrack().tip(limit)
    except Exception as exc:
        return {"error": redact_text(exc), "note": "", "rows": []}
    out = _st_result(res)
    if res.data:
        out["rows"] = [{
            "norad": _i(r.get("NORAD_CAT_ID")), "decay_epoch": r.get("DECAY_EPOCH") or "",
            "window_min": _i(r.get("WINDOW")), "lat": _f(r.get("LAT")), "lon": _wrap_lon(_f(r.get("LON"))),
            "direction": r.get("DIRECTION") or "", "msg_epoch": r.get("MSG_EPOCH") or "",
        } for r in res.data]
    return out


def get_conjunctions(limit=10):
    try:
        res = spacetrack().conjunctions(limit)
    except Exception as exc:
        return {"error": redact_text(exc), "note": "", "rows": []}
    out = _st_result(res)
    if res.data:
        out["rows"] = [{
            "tca": r.get("TCA") or "", "sat1": r.get("SAT_1_NAME") or "?", "sat2": r.get("SAT_2_NAME") or "?",
            "min_range_m": _f(r.get("MIN_RNG")), "pc": _f(r.get("PC")),
        } for r in res.data]
    return out


def get_boxscore():
    try:
        res = spacetrack().boxscore()
    except Exception as exc:
        return {"error": redact_text(exc), "note": "", "rows": []}
    out = _st_result(res)
    if res.data:
        rows = [{
            "country": r.get("COUNTRY") or "", "code": r.get("SPADOC_CD") or "",
            "payloads": _i(r.get("ORBITAL_PAYLOAD_COUNT")), "rocket_bodies": _i(r.get("ORBITAL_ROCKET_BODY_COUNT")),
            "debris": _i(r.get("ORBITAL_DEBRIS_COUNT")), "total": _i(r.get("ORBITAL_TOTAL_COUNT")),
            "decayed": _i(r.get("DECAYED_TOTAL_COUNT")), "soviet": is_soviet(r.get("SPADOC_CD"), r.get("COUNTRY")),
        } for r in res.data]
        out["rows"] = sorted(rows, key=lambda r: r["total"], reverse=True)
    return out


def _n2yo_dict(res):
    return {"error": res.error, "note": res.note, "stale": res.stale, "cached": res.cached, "age": res.age}


def get_above(category=MILITARY, radius=90):
    try:
        res = n2yo().above(category, radius)
    except Exception as exc:
        return {"error": redact_text(exc), "note": "", "rows": [], "count": 0, "category": category,
                "category_name": CATEGORIES.get(category, str(category))}
    out = _n2yo_dict(res)
    out.update({"rows": [], "count": 0, "category": category, "category_name": CATEGORIES.get(category, str(category))})
    if res.data:
        out.update(res.data)
    return out


def get_overhead():
    """Military and Globalstar satellites currently above the home location (the module's main window)."""
    return {"military": get_above(MILITARY), "globalstar": get_above(GLOBALSTAR), "home": home_location(),
            "configured": n2yo().configured}


def get_satellite(norad, passes=False):
    """N2YO details for one satellite: TLE + position now (+ visual/radio passes if passes=True)."""
    norad = int(norad)
    out = {"norad": norad, "errors": [], "notes": [], "tle": None, "position": None, "visual": None, "radio": None}
    try:
        client = n2yo()
        steps = [("tle", client.tle), ("position", client.position)]
        if passes:
            steps += [("visual", client.visual_passes), ("radio", client.radio_passes)]
        for name, fn in steps:
            res = fn(norad)
            if res.ok:
                out[name] = res.data
                if res.note:
                    out["notes"].append(res.note)
            else:
                out["errors"].append(f"{name}: {res.error}")
                if "no N2YO API key" in res.error:
                    break
    except Exception as exc:
        out["errors"].append(redact_text(f"{type(exc).__name__}: {exc}"))
    return out


def get_moons():
    """Every small body with known satellites (JPL sb_sat), grouped by primary."""
    try:
        res = nasa().smallbody.browse()
    except Exception as exc:
        return {"error": redact_text(exc), "note": "", "moons": 0, "bodies": []}
    if not res.ok:
        return {"error": res.error, "note": "", "moons": 0, "bodies": []}
    return {"error": "", "note": res.note, "moons": res.data["moons"], "bodies": res.data["bodies"]}


def get_status():
    """Everything the status screen / dashboard needs -- booleans and masked values only, never secrets."""
    user, _pw = get_credentials()
    cache_dir = default_net().cache_dir
    try:
        entries = len(list(cache_dir.glob("*.json"))) if cache_dir.exists() else 0
    except OSError:
        entries = 0
    return {
        "spacetrack": bool(user), "spacetrack_user": mask_id(user, 3) if user else "",
        "n2yo": bool(hannibal_n2yo.get_api_key()), "blueglobe_key": bool(os.getenv("BLUEGLOBE_API_KEY")), "home": home_location(),
        "fred": bool(globals().get("hannibal_fred") and hannibal_fred.get_key()),
        "masking": type(sys.stdout).__name__ == "_Stream", "cache_entries": entries,
        "frozen": rt.FROZEN,
    }


def get_breach_log_api(limit=30):
    """JSON-safe payload for the dashboard's breach panel: recent probe/breach
    attempts with their source IP geolocated. Never contains credentials."""
    try:
        entries = hannibal_geoint.get_breach_log(limit=limit, resolve=True)
    except Exception as exc:
        return {"error": redact_text(exc), "count": 0, "entries": []}
    return {"error": "", "count": hannibal_geoint.log_count(), "entries": entries}


# ================================================================ formatting ====
def _c(text, *codes, color=True):
    return art.paint(str(text), *codes, enabled=color)


def _table(headers, rows, widths, color=True, row_codes=None):
    """Fixed-width table -> list of lines. row_codes: optional list of ANSI code tuples per row."""
    def fmt(cells):
        return " | ".join(str(c)[:w].ljust(w) for c, w in zip(cells, widths))
    lines = [_c(fmt(headers), art.GOLD, color=color), "-" * (sum(widths) + 3 * (len(widths) - 1))]
    for i, r in enumerate(rows):
        codes = (row_codes[i] if row_codes else ()) or ()
        lines.append(_c(fmt(r), *codes, color=color) if codes else fmt(r))
    return lines


def _notice(data, color=True):
    """One line about staleness / errors for a provider result dict."""
    if data.get("error"):
        err = " ".join(str(data["error"]).split())
        return _c("  [!] " + (err if len(err) <= 160 else err[:157] + "..."), art.RED, color=color)
    if data.get("note"):
        return _c("  [~] " + data["note"], art.GOLD, color=color)
    if data.get("cached"):
        return _c(f"  (cached, {art.sym('dot')} refreshes per Space-Track policy)", art.GRAY, color=color)
    return ""


def fleet_lines(rows, color=True):
    colors = {"ONLINE": art.GREEN, "INTERMITTENT": art.GOLD, "OFFLINE": art.RED, "LINK ERROR": art.RED,
              "LOW SAMPLE": art.GRAY, "STATION FAULT": art.GRAY, "UNVETTED": art.GRAY, "NO PASSES": art.GRAY}
    body = [[r.get("NORAD ID", ""), r.get("Target Name", ""), r.get("TLE Epoch", ""), r.get("Status", ""),
             r.get("Packet Health", "")] for r in rows]
    lines = _table(["NORAD", "TARGET", "TLE EPOCH", "SIGNAL", "PACKET HEALTH"], body, [7, 26, 19, 13, 20], color=color)
    if color:  # colour the SIGNAL cell; a stale TLE epoch goes red
        for i, r in enumerate(rows):
            code = colors.get(r.get("Status", ""))
            stale = r.get("TLE Stale")
            if code or stale:
                cells = lines[2 + i].split(" | ")
                if code:
                    cells[3] = _c(cells[3], code)
                if stale:
                    cells[2] = _c(cells[2], art.RED)
                lines[2 + i] = " | ".join(cells)
    return lines


def sky_lines(data, color=True):
    home = data["home"]
    out = [art.section(f"SKY OVER {home['name'].upper()}  ({home['lat']:.4f}, {home['lon']:.4f})"
                       f"   as of {data['as_of'] or 'n/a'} UT", 89, color)]
    deg = art.sym("deg")
    scale = ("-90" + deg).ljust(18) + "0" + ("+90" + deg).rjust(18)
    head = f"{'BODY':<8} {'AZ':>7} {'DIR':<3}  {'EL':>7}  {scale} {'MAG':>5}  RANGE"
    out.append(_c(head, art.GOLD, color=color))
    for r in data["rows"]:
        rng = ""
        if r["range_km"] is not None:
            rng = f"{r['range_km']:,.0f} km" if r["range_au"] is not None and r["range_au"] < 0.1 else f"{r['range_au']:.3f} AU"
        az = f"{r['az']:6.1f}{deg}" if r["az"] is not None else "    n/a"
        el = f"{r['el']:+6.1f}{deg}" if r["el"] is not None else "    n/a"
        mag = f"{r['mag']:5.1f}" if r["mag"] is not None else "  n/a"
        line = f"{r['name']:<8} {az:>7} {r['dir']:<3}  {el:>7}  {art.elevation_bar(r['el'], 18, color)} {mag}  {rng}"
        out.append(line + ("   " + _c(art.sym("arrow") + " UP", art.GREEN, color=color) if r["up"] else ""))
    up = [r["name"] for r in data["rows"] if r["up"]]
    out.append("")
    out.append(f"  Above the horizon now: {', '.join(up) if up else 'none'}")
    for e in data["errors"]:
        out.append(_c("  [!] " + e, art.RED, color=color))
    return out


# =================================================================== screens ====
def screen_fleet(ask, out, color):
    rows, age = rt.load_cached_report()
    if not rows or (ask("  Rescan SatNOGS now? [y/N] ", "n").lower().startswith("y")):
        out("  Scanning SatNOGS...")
        try:
            rows, meta = rt.scan(progress=lambda i, n, r: out(f"    [{i}/{n}] {r['Target Name']}: {r['Status']}"))
            if rt.write_report(rows, meta):
                out(f"  Report written to {rt.report_path().name}")
            else:
                out("  [!] every request failed (offline?) -- previous report kept")
                rows, age = rt.load_cached_report()
        except Exception as exc:
            out(_c("  [!] scan failed: " + redact_text(exc), art.RED, color=color))
            return
    out(art.section("FLEET TELEMETRY -- SATNOGS LINK HEALTH (24 h)", 89, color))
    for line in fleet_lines(rows, color):
        out(line)


def screen_reentry(ask, out, color):
    out(art.section("RE-ENTRY WATCH -- SPACE-TRACK DECAY + TIP", 89, color))
    d = get_decay(25)
    n = _notice(d, color)
    n and out(n)
    if d["rows"]:
        rows = [[r["norad"], r["name"], r["country"], r["decay_epoch"], r["msg_type"], r["rcs"]] for r in d["rows"]]
        codes = [(art.RED,) if r["soviet"] else () for r in d["rows"]]
        for line in _table(["NORAD", "OBJECT", "COUNTRY", "DECAY EPOCH (UTC)", "TYPE", "RCS"], rows,
                           [7, 26, 8, 19, 12, 7], color, codes):
            out(line)
        out(_c("  red = USSR / Russian Federation (Space-Track code CIS)", art.GRAY, color=color))
    t = get_tip(8)
    out("")
    out(art.section("LATEST TIP MESSAGES (tracking & impact prediction)", 89, color))
    n = _notice(t, color)
    n and out(n)
    if t["rows"]:
        rows = [[r["norad"], r["decay_epoch"], f"+/-{r['window_min']} min", f"{r['lat']:.1f}" if r["lat"] is not None else "",
                 f"{r['lon']:.1f}" if r["lon"] is not None else "", r["direction"]] for r in t["rows"]]
        for line in _table(["NORAD", "PREDICTED DECAY", "WINDOW", "LAT", "LON", "DIR"], rows, [7, 19, 11, 7, 8, 5], color):
            out(line)


def screen_conjunctions(ask, out, color):
    out(art.section("CLOSE APPROACHES -- SPACE-TRACK PUBLIC CDMs", 89, color))
    d = get_conjunctions(10)
    n = _notice(d, color)
    n and out(n)
    if d["rows"]:
        rows = [[r["tca"], r["sat1"], r["sat2"], f"{r['min_range_m']:,.0f} m" if r["min_range_m"] is not None else "",
                 f"{r['pc']:.1e}" if r["pc"] is not None else ""] for r in d["rows"]]
        for line in _table(["TCA (UTC)", "OBJECT 1", "OBJECT 2", "MISS DIST", "Pc"], rows, [19, 24, 24, 12, 9], color):
            out(line)


def screen_boxscore(ask, out, color):
    out(art.section("CATALOGUE BOX SCORE -- OBJECTS IN ORBIT BY COUNTRY", 89, color))
    d = get_boxscore()
    n = _notice(d, color)
    n and out(n)
    if d["rows"]:
        rows = [[r["country"], r["code"], r["payloads"], r["rocket_bodies"], r["debris"], r["total"]] for r in d["rows"][:15]]
        codes = [(art.RED,) if r["soviet"] else () for r in d["rows"][:15]]
        for line in _table(["COUNTRY", "CODE", "PAYLOADS", "ROCKETS", "DEBRIS", "TOTAL"], rows,
                           [26, 6, 9, 8, 8, 8], color, codes):
            out(line)
        out(_c(f"  top 15 of {len(d['rows'])} entries; red = USSR / Russian Federation", art.GRAY, color=color))


def screen_sky(ask, out, color):
    for line in sky_lines(get_sky(), color):
        out(line)


def screen_ephemeris(ask, out, color):
    target = ask("  Target (moon, mars, jupiter, 433, Apophis, 1999 AN10, id:499) [moon]: ", "moon")
    mode = ask("  [O]bserver view from home or [V]ectors from Earth centre? [O]: ", "o").lower()
    h = nasa().horizons
    home = home_location()
    if mode.startswith("v"):
        res = h.vectors(target)
        cols = [("JDTDB", 17), ("Calendar Date (TDB)", 26), ("RG", 15), ("RR", 12), ("LT", 10)]
    else:
        res = h.observer(target, home["lat"], home["lon"], home["alt_km"], step="10 m")
        cols = None
    if res.error:
        out(_c("  [!] " + res.error, art.RED, color=color))
        return
    out(art.section(f"HORIZONS -- {target.upper()}  ({'vectors' if mode.startswith('v') else 'observer'})", 89, color))
    if res.note:
        out(_c("  [~] " + res.note, art.GOLD, color=color))
    rows = res.data[:6]
    if cols:
        names = [c for c, _ in cols if c in rows[0]]
        for line in _table(names, [[r.get(n, "") for n in names] for r in rows], [w for c, w in cols if c in rows[0]], color):
            out(line)
        out("  RG = range from Earth centre (km), RR = range-rate (km/s), LT = one-way light time (s)")
    else:
        names = list(rows[0].keys())
        show = [n for n in names if not n.startswith("_flag")][:7]
        for line in _table(show, [[r.get(n, "") for n in show] for r in rows], [20] + [14] * (len(show) - 1), color):
            out(line)


def _paged(rows_fn, total, ask, out, page=15):
    """Print rows page by page. rows_fn(start, end) -> list of lines. Returns when exhausted or 'q'."""
    pos = 0
    while pos < total:
        for line in rows_fn(pos, min(total, pos + page)):
            out(line)
        pos += page
        if pos >= total:
            break
        if ask(f"  -- {min(pos, total)}/{total}  [Enter] more, [q] stop: ", "").lower().startswith("q"):
            break


def _moon_detail(body, out, color):
    out(art.section(f"{body['name'].upper()}  ({body['class']} - {body.get('class_name') or ''})", 89, color))
    rows = [[m["name"], m["confirmed"] or "-", f"{m['a_km']:,.0f}" if m["a_km"] else "-", f"{m['e']:.3f}" if m["e"] is not None else "-",
             f"{m['i_deg']:.1f}" if m["i_deg"] is not None else "-", f"{m['period_d']:.3f}" if m["period_d"] else "-"] for m in body["moons"]]
    for line in _table(["SATELLITE", "CONF", "A (km)", "E", "INC", "PERIOD (d)"], rows, [34, 5, 10, 7, 6, 11], color):
        out(line)
    for m in body["moons"]:
        if m.get("ref"):
            out(_c(f"  ref: {m['ref'][:100]}", art.GRAY, color=color))
            break
    phys = nasa().smallbody.satellites(des=body["pdes"], orbit=False, phys=True)
    shown = False
    for m in (phys.data or []) if phys.ok else []:
        pp = m.get("phys") or {}
        bits = []
        for key, label in (("diameter", "diameter km"), ("rot_per", "rotation h"), ("GM", "GM km3/s2"), ("density", "density g/cm3"), ("extent", "extent km")):
            v = pp.get(key)
            v = v.get("value") if isinstance(v, dict) else v
            if v not in (None, ""):
                bits.append(f"{label}: {v}")
        if bits:
            out(f"  {m['name']}: " + "   ".join(bits))
            shown = True
    if not shown:
        out(_c("  (JPL lists no physical parameters for these satellites)", art.GRAY, color=color))


def screen_asteroid_moons(ask, out, color):
    """Browse every asteroid / comet / TNO with known satellites (JPL sb_sat), or open one by number."""
    out(art.section("SMALL-BODY SATELLITES -- JPL sb_sat", 89, color))
    res = nasa().smallbody.browse()
    if not res.ok:
        out(_c("  [!] " + res.error, art.RED, color=color))
        return
    if res.note:
        out(_c("  [~] " + res.note, art.GOLD, color=color))
    classes = {}
    for b in res.data["bodies"]:
        classes[b["class"]] = classes.get(b["class"], 0) + 1
    out(f"  {res.data['moons']} known satellites around {len(res.data['bodies'])} bodies.   Classes: " +
        ", ".join(f"{k} {v}" for k, v in sorted(classes.items(), key=lambda kv: -kv[1])))
    while True:
        q = ask("  Class code (TNO, MBA, APO...), a name, a number (22 / 87 / 2000 DP107), or 'all'; Enter = back: ", "")
        if not q or q.lower() == "q":
            return
        cls = q.upper() if q.upper() in classes else None
        exact = [b for b in res.data["bodies"] if b["pdes"].lower() == q.lower()]   # "22" means asteroid 22, not every name containing 22
        if exact:
            bodies = exact
        else:
            text = None if (cls or q.lower() == "all") else q
            view = nasa().smallbody.browse(cls=cls, query=text)
            bodies = view.data["bodies"] if view.ok else []
        if not bodies:
            out("  No body with satellites matches that.")
            continue
        if len(bodies) == 1:
            _moon_detail(bodies[0], out, color)
            continue

        def rows(i, j, bodies=bodies):
            lines = [_c(f"  {'#':>3} | {'PRIMARY':<32} | {'CLASS':<5} | {'MOONS':>5} | SATELLITES", art.GOLD, color=color)]
            for k in range(i, j):
                b = bodies[k]
                names = ", ".join(str(m["name"]).split(") ")[-1] for m in b["moons"])
                lines.append(f"  {k + 1:>3} | {b['name'][:32]:<32} | {str(b['class']):<5} | {len(b['moons']):>5} | {names[:34]}")
            return lines
        _paged(rows, len(bodies), ask, out)
        pick = ask("  Open which # (Enter = back to filter): ", "")
        if pick.isdigit() and 1 <= int(pick) <= len(bodies):
            _moon_detail(bodies[int(pick) - 1], out, color)


def screen_radar(ask, out, color):
    des = ask("  Asteroid/comet number or designation [433]: ", "433")
    res = nasa().smallbody.radar(des=des, limit=12)
    out(art.section(f"RADAR ASTROMETRY -- {des}", 89, color))
    if res.error:
        out(_c("  [!] " + res.error, art.RED, color=color))
        return
    rows = res.data["rows"]
    if not rows:
        out("  No radar observations on file.")
        return
    body = [[r.get("epoch", ""), r.get("kind_of", ""), f"{r['value']:,.2f}" if r["value"] is not None else "",
             f"{r['sigma']:.2f}" if r["sigma"] is not None else "", r.get("units", ""), r.get("freq", ""),
             f"{r.get('xmit', '')}>{r.get('rcvr', '')}", (r.get("observer") or "")[:30]] for r in rows]
    for line in _table(["EPOCH (UTC)", "TYPE", "VALUE", "SIGMA", "UNITS", "MHz", "TX>RX", "OBSERVERS"], body,
                       [19, 8, 16, 8, 5, 6, 7, 30], color):
        out(line)
    out(f"  showing newest {len(rows)} of {res.data['count']} measurements")


def screen_periodic(ask, out, color):
    system = ask("  Three-body system [earth-moon]: ", "earth-moon")
    family = ask(f"  Family ({', '.join(FAMILIES)}) [halo]: ", "halo")
    libr = ask("  Libration point 1-5 (blank if not needed) [2]: ", "2")
    branch = ask("  Branch N/S (blank for none) [S]: ", "S")
    res = nasa().periodic.query(system, family, libr=int(libr) if libr.isdigit() else None, branch=branch or None)
    out(art.section(f"PERIODIC ORBITS -- {system.upper()} / {family.upper()}", 89, color))
    if res.error:
        out(_c("  [!] " + res.error, art.RED, color=color))
        return
    d = res.data
    out(f"  {d['count']} orbits found; the {len(d['rows'])} most stable (stability index <= 1 means stable):")
    rows = [[f"{r.get('period_days', 0):.3f}", f"{r.get('jacobi', 0):.5f}", f"{r.get('stability', 0):.3f}",
             f"{r.get('x_km', 0):,.0f}", f"{r.get('z_km', 0):,.0f}"] for r in d["rows"]]
    for line in _table(["PERIOD (d)", "JACOBI", "STABILITY", "X0 (km)", "Z0 (km)"], rows, [11, 10, 10, 12, 10], color):
        out(line)


def screen_status(ask, out, color):
    s = get_status()
    out(art.section("SYSTEM STATUS", 89, color))
    yes, no = _c("SET", art.GREEN, color=color), _c("NOT SET", art.RED, color=color)
    out(f"  Space-Track credentials : {yes if s['spacetrack'] else no}"
        + (f"   (user {s['spacetrack_user']})" if s["spacetrack"] else f"   -> {CREDENTIALS_HELP}"))
    out(f"  N2YO API key            : {yes if s['n2yo'] else no}"
        + ("" if s["n2yo"] else "   -> menu [K] to type it (free: n2yo.com > profile > API key), or set N2YO_API_KEY"))
    out(f"  FRED API key            : {yes if s.get('fred') else no}"
        + ("" if s.get("fred") else "   -> menu [M], or: python hannibal_fred.py --set-key (or setx FRED_API_KEY)"))
    out(f"  BlueGlobe API key       : {yes if s['blueglobe_key'] else _c('default test key', art.GOLD, color=color)}   (BLUEGLOBE_API_KEY)")
    out(f"  Output masking          : {yes.replace('SET', 'ACTIVE') if s['masking'] else _c('not installed in this process', art.GOLD, color=color)}")
    out(f"  Home location           : {s['home']['name']} ({s['home']['lat']:.4f}, {s['home']['lon']:.4f})")
    out(f"  Response cache          : {s['cache_entries']} entries in {default_net().cache_dir}")
    out("  JPL services need no key. Space-Track policy: <30 req/min, <300/h, GP 1/h, SATCAT/DECAY 1/day (enforced).")


def screen_dashboard(ask, out, color):
    out("  " + sat_launch_dashboard())


def screen_feeder(ask, out, color):
    out(art.section("ADS-B FEEDER -> satellitemap.space  (optional)", 89, color))
    out("  Needs your own readsb/tar1090 receiver at http://localhost/tar1090/ (set HANNIBAL_ADSB_SOURCE to change).")
    dry = ask("  Dry run first (read only, sends nothing)? [Y/n]: ", "y").lower() != "n"
    loop = ask("  Keep running until Ctrl+C? [y/N]: ", "n").lower().startswith("y")
    try:
        hannibal_feeder.run(loop=loop, dry_run=dry, confirm=lambda: ask("  Type FEED to start, anything else to cancel: ", ""), print_fn=out)
    except KeyboardInterrupt:
        out("  Feeder stopped.")


def screen_gallery(ask, out, color):
    """The Soviet space-programme art gallery."""
    pieces = [("SPUTNIK", art.sputnik, art.GOLD), ("VOSTOK ON THE PAD", art.launch, art.RED),
              ("ZVEZDA", art.red_star, art.RED), ("GROUND STATION", art.dish, art.CYAN), ("ORBITA", art.orbit, art.GOLD)]
    for title, fn, code in pieces:
        out(art.section(title, 89, color))
        for line in fn().splitlines():
            out(_c("   " + line, code, color=color))
        out("")
    out(_c("  " + art.big_text("KOSMOS NASH!").replace("\n", "\n  "), art.RED, color=color))
    out("")
    for slogan in art.SLOGANS:
        out(_c(f"  {art.sym('star')} {slogan}", art.GOLD, color=color))


def _above_table(data, out, color, limit=8, numbered=False):
    """Print one N2YO 'above' result. Returns the rows shown."""
    title = f"{data['category_name'].upper()} OVERHEAD NOW  ({data.get('count', 0)} above the horizon)"
    out(art.section(title, 89, color))
    n = _notice(data, color)
    n and out(n)
    rows = data.get("rows", [])[:limit]
    if rows:
        head = ("#   " if numbered else "") + f"{'NORAD':<6} {'NAME':<24} {'EL':>5} {'AZ':>4} {'ALT km':>7} {'GROUND km':>10}  OVER (lat, lon)"
        out(_c("  " + head, art.GOLD, color=color))
        for i, r in enumerate(rows, 1):
            out(("  " + (f"{i:<3} " if numbered else "") +
                 f"{r['norad']:<6} {r['name'][:24]:<24} {r['el']:>5.1f} {r['dir']:>4} {r['alt_km']:>7,.0f} {r['distance_km']:>10,}  "
                 f"{r['lat']:+.1f}, {r['lon']:+.1f}"))
        if data.get("count", 0) > len(rows):
            out(_c(f"  ... and {data['count'] - len(rows)} more (use [N] for the full list)", art.GRAY, color=color))
    elif not data.get("error"):
        out("  Nothing in this category is above your horizon right now.")
    return rows


def screen_home(ask, out, color):
    """The main window: Military and Globalstar satellites above the home location."""
    d = get_overhead()
    home = d["home"]
    out(art.section(f"ON THE SKY OVER {home['name'].upper()} -- N2YO", 89, color))
    if not d["configured"]:
        out(_c("  [!] no N2YO API key yet -- pick [K] to enter it (free key: n2yo.com > profile > API key).", art.RED, color=color))
        return
    for key in ("military", "globalstar"):
        _above_table(d[key], out, color)
        out("")


def _satellite_detail(norad, out, color):
    d = get_satellite(norad, passes=True)
    name = (d["tle"] or {}).get("name") or (d["position"] or {}).get("name") or ""
    out(art.section(f"SATELLITE {norad}  {name}", 89, color))
    for e in d["errors"]:
        out(_c("  [!] " + e, art.RED, color=color))
    for n in sorted(set(d["notes"])):
        out(_c("  [~] " + n, art.GOLD, color=color))
    p = d["position"]
    if p:
        out(f"  NOW      lat {p['lat']:+.2f}  lon {p['lon']:+.2f}  alt {p['alt_km']:,.0f} km   az {p['az']:.0f} {hannibal_n2yo.compass(p['az'])}  "
            f"el {p['el']:+.1f}   " + (_c(art.sym("arrow") + " ABOVE YOUR HORIZON", art.GREEN, color=color) if p["up"] else "below the horizon") +
            f"   ({p['time']} UTC)")
    t = d["tle"]
    if t and t["line1"]:
        out("  TLE      " + t["line1"])
        out("           " + t["line2"])
    for key, title in (("visual", "NEXT VISUAL PASSES (naked eye)"), ("radio", "NEXT RADIO PASSES (>= 10 deg)")):
        v = d[key]
        if v is None:
            continue
        out("")
        out(_c(f"  {title} -- {v['count']} in 5 days", art.GOLD, color=color))
        if not v["passes"]:
            out("  none")
        for r in v["passes"][:5]:
            extra = f"  mag {r['mag']:.1f}  {r['duration']} s" if key == "visual" and r["mag"] is not None else ""
            out(f"  {r['start']} UTC  {r['start_dir']:>3} -> max {r['max_el']:.0f} deg {r['max_dir']:>3} -> {r['end_dir']:>3}{extra}")
    return d


def screen_n2yo(ask, out, color):
    """Look at a satellite: pick from what is overhead, a category, your fleet, or a NORAD id."""
    if not n2yo().configured:
        out(_c("  [!] no N2YO API key yet -- pick [K] to enter it (free key: n2yo.com > profile > API key).", art.RED, color=color))
        return
    out(art.section("N2YO SATELLITE LOOKUP", 89, color))
    out("   [1] Military overhead now        [2] Globalstar overhead now")
    out("   [3] Another category (GPS, Iridium, Starlink, ISS, weather, amateur...)")
    out("   [4] Enter a NORAD id             [5] My fleet (norad_targets.json)")
    choice = ask("  Choose [1-5, Enter = back]: ", "").strip()
    norad = None
    if choice in ("1", "2", "3"):
        cat = MILITARY if choice == "1" else GLOBALSTAR
        if choice == "3":
            for i, cid in enumerate(MENU_CATEGORIES, 1):
                out(f"   [{i:>2}] {CATEGORIES[cid]}")
            pick = ask("  Category number or name: ", "")
            cat = hannibal_n2yo.category_id(pick) if not pick.isdigit() else (MENU_CATEGORIES[int(pick) - 1] if 1 <= int(pick) <= len(MENU_CATEGORIES) else None)
            if cat is None:
                out("  Unknown category.")
                return
        data = get_above(cat)
        rows = _above_table(data, out, color, limit=30, numbered=True)
        if rows:
            pick = ask("  Look at which # (or a NORAD id, Enter = back): ", "")
            if pick.isdigit():
                norad = rows[int(pick) - 1]["norad"] if 1 <= int(pick) <= len(rows) else int(pick)
    elif choice == "4":
        pick = ask("  NORAD id: ", "")
        norad = int(pick) if pick.isdigit() else None
    elif choice == "5":
        targets = rt.load_config()["targets"]
        for i, t in enumerate(targets, 1):
            out(f"   [{i}] {t['id']:<6} {t['name']}")
        pick = ask("  Which #: ", "")
        if pick.isdigit() and 1 <= int(pick) <= len(targets):
            norad = targets[int(pick) - 1]["id"]
    if not norad:
        return
    _satellite_detail(norad, out, color)
    if ask("  [G] show it on the 3D globe, Enter = back: ", "").lower().startswith("g"):
        out("  " + sat_launch_dashboard([norad]))


# the hidden-password prompt; run_menu swaps it so tests can type a password without a terminal
_secret = [getpass.getpass]


def _geo_row(entry):
    geo = entry.get("geo") or {}
    pm = entry.get("phone_meta") or {}
    where = ", ".join(x for x in (geo.get("city"), geo.get("region"), geo.get("country")) if x) \
        or (geo.get("note") or geo.get("error") or "")
    phone_col = pm.get("e164") or entry.get("phone", "") or "-"
    if pm.get("line_type"):
        phone_col += f" ({pm['line_type']})"
    return [entry.get("ts", ""), entry.get("ip", "") or "-", phone_col[:20], entry.get("kind", ""),
            str(entry.get("count", 1)), where[:24], (geo.get("isp") or "")[:18]]


def _print_geo(g, out, color):
    if g.get("error"):
        out(_c("  [!] " + g["error"], art.RED, color=color))
        return
    if g.get("note"):
        out(_c("  " + g["note"], art.GOLD, color=color))
        return
    out(f"  {g['ip']}  ->  {g.get('city') or '?'}, {g.get('region') or '?'}, {g.get('country') or '?'}")
    out(f"  ISP/org: {g.get('isp') or 'n/a'}   ASN: {g.get('asn') or 'n/a'}   TZ: {g.get('timezone') or 'n/a'}")
    if g.get("lat") is not None and g.get("lon") is not None:
        out(f"  Approx coordinates: {g['lat']:.3f}, {g['lon']:.3f}  (city/ISP-level, not precise)")
    if g.get("cached"):
        out(_c(f"  (cached, {g.get('age', 0) / 3600:.1f} h old)", art.GRAY, color=color))


def _print_phone(m, out, color):
    if m.get("error"):
        out(_c("  [!] " + m["error"], art.RED, color=color))
        return
    out(f"  {m['e164']}   valid: {m['valid']}   line type: {m['line_type']}")
    out(f"  Number range registered to: {m['number_range_region'] or 'n/a'}   Carrier: {m['carrier']}")
    if m.get("timezones"):
        out(f"  Timezone(s) for this range: {', '.join(m['timezones'])}")
    out(_c("  (number-range metadata only -- not a live location of the handset)", art.GRAY, color=color))


def screen_breach_log(ask, out, color):
    """Compliance tab: probe/breach attempts logged by the dashboard server (and anything
    else that calls hannibal_geoint.record_attempt), each IP geolocated for the write-up,
    plus hand lookups for an IP or a phone number's metadata."""
    out(art.section("BREACH LOG -- PROBES & LOOKUPS (COMPLIANCE RECORD)", 89, color))
    payload = get_breach_log_api(40)
    if payload["error"]:
        out(_c("  [!] " + payload["error"], art.RED, color=color))
    out(f"  {payload['count']} total entries on disk (showing last {len(payload['entries'])}) -- {hannibal_geoint.log_path()}")
    out(_c("  log file is set read-only between writes; entries are append-only", art.GRAY, color=color))
    if payload["entries"]:
        rows = [_geo_row(e) for e in payload["entries"]]
        for line in _table(["TIME (UTC)", "SOURCE IP", "PHONE", "KIND", "x", "LOCATION", "ISP/ORG"], rows,
                           [20, 15, 20, 12, 3, 24, 18], color):
            out(line)
    else:
        out("  No probe/breach attempts recorded yet.")
    out("")
    out("  Lookups only work on an IP or number that is already logged below -- log it with [M] first.")
    out("  [I] look up a logged IP        [P] logged phone's metadata (country/carrier -- not a location)")
    out("  [M] add a manual breach note   Enter: back")
    choice = ask("  COMMAND > ", "").strip().upper()
    if choice == "I":
        ip = ask("  IP address (must already be logged): ", "").strip()
        if ip:
            _print_geo(hannibal_geoint.lookup_ip(ip), out, color)
    elif choice == "P":
        num = ask("  Phone number, with country code (must already be logged): ", "").strip()
        if num:
            _print_phone(hannibal_geoint.phone_metadata(num), out, color)
    elif choice == "M":
        ip = ask("  Source IP (blank if none): ", "").strip()
        phone = ask("  Phone number involved, if any (blank if none): ", "").strip()
        detail = ask("  What happened: ", "").strip()
        if ip or phone or detail:
            hannibal_geoint.record_attempt(ip, "manual", detail=detail, source="menu", phone=phone)
            out("  Logged to the compliance record -- that IP/number can now be looked up with [I]/[P].")


def screen_logins(ask, out, color):
    """Enter (or re-enter) the Space-Track login and the N2YO key. Kept in memory for this run only."""
    hannibal_login.ensure_logins(input_fn=lambda p: ask(p, ""), secret_fn=lambda p: _secret[0](p), print_fn=out, force=True)
    reset_clients()


MENU = [
    ("1", "Fleet telemetry        SatNOGS link health of your satellites", screen_fleet),
    ("2", "Re-entry watch         Space-Track DECAY + TIP predictions", screen_reentry),
    ("3", "Close approaches       Space-Track public conjunction messages", screen_conjunctions),
    ("4", "Box score              objects in orbit by country (USSR/RU in red)", screen_boxscore),
    ("H", "Home window           Military + Globalstar satellites overhead now (N2YO)", screen_home),
    ("N", "N2YO satellites       look at any satellite: position, TLE, visual/radio passes", screen_n2yo),
    ("5", "Sky tonight            Sun, Moon & planets over your home (JPL Horizons)", screen_sky),
    ("6", "Ephemeris lookup       any planet, moon, asteroid or comet (Horizons)", screen_ephemeris),
    ("7", "Asteroid moons         browse every body with moons (JPL sb_sat)", screen_asteroid_moons),
    ("8", "Radar astrometry       JPL small-body radar delay/Doppler data", screen_radar),
    ("9", "Periodic orbits        JPL three-body orbit families (halo, DRO, ...)", screen_periodic),
    ("G", "BlueGlobe 3D globe     open the dashboard in your browser", screen_dashboard),
    ("F", "ADS-B feeder           optional: share your receiver with satellitemap", screen_feeder),
    ("K", "Logins & keys         type your Space-Track password and N2YO key (hidden, memory only)", screen_logins),
    ("I", "Breach log             probe/attack IPs (geolocated), phone metadata, compliance record", screen_breach_log),
    ("S", "Status                 credentials, masking, cache, limits", screen_status),
    ("A", "Art gallery            Sputnik, Vostok, the red star, slogans", screen_gallery),
    ("Q", "Quit", None),
]

# --- Earth export (added 2026-10-11, see CHANGELOG.md of hannibal-satellite) ---------------------
# Adds an [E] screen that writes KML for Google Earth and CZML for the Cesium globe. Guarded: if the
# hannibal_sat package is not installed, this module behaves exactly as before.
try:
    from hannibal_sat.hannibal_bridge import register as _register_earth_export
    _register_earth_export(MENU)
except Exception:  # noqa: BLE001 - an optional add-on must never stop the orbital module loading
    pass

# --- FRED macro board (added 2026-10-11) -------------------------------------------------------------
# [M] screen: CPI, core PCE, policy rate, curve, M2 velocity, Brent, dollar. Key from FRED_API_KEY or the
# OS credential store (python hannibal_fred.py --set-key); never in source. Guarded like the Earth export.
try:
    import hannibal_fred
    MENU.insert(next(i for i, m in enumerate(MENU) if m[0] == "S"),
                ("M", "Macro (FRED)           CPI, core PCE, rates, curve, M2 velocity, Brent, dollar",
                 hannibal_fred.screen_macro))
except Exception:  # noqa: BLE001
    hannibal_fred = None

# --- Market brain (added 2026-10-11, developers only) ------------------------------------------------
# [R] screen: developer key gate, then the ten-lobe market brain in your browser (127.0.0.1 only,
# single-use launch link, session cookie, strict CSP, breach log). See hannibal_brain.py.
try:
    import hannibal_brain
    MENU.insert(next(i for i, m in enumerate(MENU) if m[0] == "S"),
                ("R", "Market brain [DEV]     what the market is thinking: 10 lobes, live transmission paths",
                 hannibal_brain.screen_brain))
except Exception:  # noqa: BLE001
    hannibal_brain = None

# --- Grand Unified Happiness Theorem (added 2026-10-11, developers only) ----------------------------------
# [T] screen: same developer gate as [R], then the 10-lobe cranial report. See hannibal_theorem.py.
try:
    import hannibal_theorem
    MENU.insert(next(i for i, m in enumerate(MENU) if m[0] == "S"),
                ("T", "Happiness theorem [DEV] the Grand Unified Happiness Theorem & 10-lobe cranial report",
                 hannibal_theorem.screen_theorem))
except Exception:  # noqa: BLE001
    hannibal_theorem = None

# --- Kessler cascade watch (added 2026-10-22, proof of concept) ---------------------------------------
# [D] screen: tracked objects per 50 km shell from the public CelesTrak catalog, with a simple cascade
# index (objects / count at which collision fragments outpace drag cleanup). Receive-only, no key.
try:
    import hannibal_kessler
    MENU.insert(next(i for i, m in enumerate(MENU) if m[0] == "G"),
                ("D", "Debris cascade         Kessler watch: objects per altitude shell, cascade index (CelesTrak)",
                 hannibal_kessler.screen_kessler))
except Exception:  # noqa: BLE001
    hannibal_kessler = None

# --- Where it won't be (added 2026-10-22) ---------------------------------------------------------------
# [W] screen: Earth-impact exclusion for any asteroid or comet from NASA/JPL close-approach data, with the
# overall verdict deferring to JPL Sentry (a clean pass can still lead through a keyhole to a later impact).
try:
    import hannibal_neo
    MENU.insert(next(i for i, m in enumerate(MENU) if m[0] == "D"),
                ("W", "Where it won't be     impact exclusion for any asteroid or comet (JPL CNEOS + Sentry)",
                 hannibal_neo.screen_neo))
except Exception:  # noqa: BLE001
    hannibal_neo = None


def run_menu(input_fn=None, print_fn=print, color=None, animate=False, logins=None, home=None, secret_fn=None):
    """Interactive menu loop. input_fn / print_fn are injectable so the menu is testable.

    logins: ask once for the Space-Track login and N2YO key when they are missing (default: only on a real keyboard).
    home:   show the Military + Globalstar "overhead now" window when the menu opens (same default).
    """
    real_keyboard = input_fn is None
    logins = real_keyboard if logins is None else logins
    home = real_keyboard if home is None else home
    input_fn = input_fn or input   # looked up at call time, so it can be replaced (and tested)
    if secret_fn:
        _secret[0] = secret_fn
    if color is None:
        color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    if animate:
        art.boot_animation()

    def ask(prompt, default=""):
        try:
            answer = input_fn(prompt)
        except (EOFError, KeyboardInterrupt):
            return default
        return answer.strip() or default

    if logins:   # typed once, hidden, memory only; env vars win so nothing is asked when they are set
        print_fn(art.title_card("ORBITAL OPS", color=color))
        if hannibal_login.ensure_logins(input_fn=input_fn, secret_fn=lambda p: _secret[0](p), print_fn=print_fn).get("changed"):
            reset_clients()
    if home:
        try:
            screen_home(ask, print_fn, color)
        except Exception as exc:
            print_fn(_c("  [!] home window failed: " + redact_text(f"{type(exc).__name__}: {exc}"), art.RED, color=color))

    while True:
        print_fn("")
        print_fn(art.title_card("ORBITAL OPS", color=color))
        print_fn("")
        for key, label, _fn in MENU:
            name, _, desc = label.partition("  ")
            print_fn(f"   {_c('[' + key + ']', art.GOLD, color=color)} {name:<22} {desc.strip()}")
        try:
            choice = input_fn("\n  COMMAND > ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            return 0
        if choice in ("Q", "QUIT", "EXIT", ""):
            if choice == "":
                continue
            print_fn(_c(f"\n  {art.sym('star')} DOSVIDANIYA, COMRADE {art.sym('star')}", art.GOLD, color=color))
            return 0
        entry = next((m for m in MENU if m[0] == choice), None)
        if entry is None or entry[2] is None:
            print_fn("  Unknown command.")
            continue
        print_fn("")
        try:
            entry[2](ask, print_fn, color)
        except KeyboardInterrupt:
            print_fn("  (interrupted)")
        except Exception as exc:  # a broken screen must never kill the menu
            print_fn(_c("  [!] screen failed: " + redact_text(f"{type(exc).__name__}: {exc}"), art.RED, color=color))
        ask("\n  Press Enter to return to the menu... ", "")


# ======================================================= terminal integration ====
# These are what the main terminal's [L] view, [B] key and [V] key call. Scans run on a
# background thread so the render loop never blocks on the network.
SAT_STALE_SECONDS = 1800
if os.getenv("HANNIBAL_NET_PROFILE", "normal").strip().lower() == "low":
    SAT_STALE_SECONDS = 6 * 3600   # low-internet launcher: auto-rescan every 6 h, not 30 min ([L] still rescans now)
_sat_lock = threading.Lock()
_sat_state = {"rows": [], "updated_at": None, "loaded": False, "scanning": False,
              "progress": "", "error": "", "spacetrack": "", "msg": "", "msg_at": 0.0}


def _sat_load_cache():
    rows, age = rt.load_cached_report()
    with _sat_lock:
        _sat_state["rows"] = rows
        _sat_state["updated_at"] = (time.time() - age) if age is not None else None
        _sat_state["loaded"] = True


def _sat_scan_worker():
    def _progress(done, total, row):
        with _sat_lock:
            _sat_state["progress"] = f"{done}/{total} {row['Target Name']}"
    try:
        rows, meta = rt.scan(progress=_progress)
        wrote = rt.write_report(rows, meta)
        with _sat_lock:
            _sat_state["spacetrack"] = meta.get("spacetrack", "")
            if wrote:
                _sat_state["rows"], _sat_state["updated_at"], _sat_state["error"] = rows, time.time(), ""
            else:
                _sat_state["error"] = "All SatNOGS requests failed (offline?) -- showing the previous report."
    except Exception as exc:
        with _sat_lock:
            _sat_state["error"] = redact_text(f"Scan failed: {type(exc).__name__}: {exc}")[:200]
    finally:
        with _sat_lock:
            _sat_state["scanning"], _sat_state["progress"] = False, ""


def sat_refresh_async(force=False):
    """Start a background scan unless one is running (or the cache is fresh and not forced)."""
    with _sat_lock:
        if _sat_state["scanning"]:
            return
        updated = _sat_state["updated_at"]
        if not force and updated is not None and time.time() - updated < SAT_STALE_SECONDS:
            return
        _sat_state["scanning"] = True
    threading.Thread(target=_sat_scan_worker, name="Sat-Scan", daemon=True).start()


def sat_launch_dashboard(norad_ids=None):
    """Start the localhost-only BlueGlobe server (once) and open it in the default browser. Returns a message.

    norad_ids: optional satellites to load on the globe (digits only, at most 50; passed as ?norad=a,b,c).
    """
    try:
        import webbrowser

        import hannibal_blueglobe as globe
        url = globe.ensure_server()
        ids = [str(int(n)) for n in (norad_ids or [])][:50]
        if ids:
            url += "?norad=" + ",".join(ids)
        webbrowser.open(url)
        msg = f"Dashboard opened: {url}"
    except Exception as exc:
        msg = "Could not start dashboard: " + redact_text(exc)
    with _sat_lock:
        _sat_state["msg"], _sat_state["msg_at"] = msg, time.time()
    return msg


def render_ops_home():
    """The [V] page of the main terminal: banner plus a pointer to the interactive menu."""
    print(art.title_card("ORBITAL OPS", width=89, color=True))
    print()
    for line in art.launch().splitlines():
        print(art.paint("   " + line, art.GOLD, enabled=True))
    print()
    print(f" {art.paint('Press [V] again to open the Orbital Ops menu', art.WHITE, enabled=True)}"
          f" {art.paint('(Military + Globalstar overhead, N2YO satellite lookup, re-entries, close approaches, box score, NASA/JPL, ADS-B feeder).', art.GRAY, enabled=True)}")
    print(f" {art.paint('[L] fleet link health | [B] 3D BlueGlobe dashboard | every request is masked, cached and rate-limited.', art.GRAY, enabled=True)}")


def render_sat_view():
    """Print the [L] page of the main terminal."""
    G, Y, R, C, RS = art.GRAY, art.GOLD, art.RED, art.CYAN, art.RESET
    hs = art.sym("hs")
    print(f"\033[95m  {hs} ORBITAL TELEMETRY -- AMATEUR / EDUCATIONAL SATELLITE LINK HEALTH (SatNOGS + Space-Track){RS}")
    print(f"\033[94m{'=' * 89}{RS}")
    if not _sat_state["loaded"]:
        _sat_load_cache()
    sat_refresh_async()   # no-op unless the report is missing or stale
    with _sat_lock:
        rows = list(_sat_state["rows"])
        updated, scanning, progress = _sat_state["updated_at"], _sat_state["scanning"], _sat_state["progress"]
        error, st_state = _sat_state["error"], _sat_state["spacetrack"]
        msg = _sat_state["msg"] if time.time() - _sat_state["msg_at"] < 15 else ""
    if updated is None:
        age_txt = "no report yet"
    else:
        mins = int((time.time() - updated) // 60)
        age_txt = "just now" if mins < 1 else (f"{mins} min ago" if mins < 120 else f"{mins // 60} h ago")
    scan_txt = f"{Y}SCANNING... {progress}{RS}" if scanning else f"{G}idle{RS}"
    print(f" Report updated: {C}{age_txt}{RS} | Scanner: {scan_txt}")
    if st_state == "no credentials":
        print(f" {G}TLE epochs need Space-Track: press [V], then [K] to type your login (or set SPACETRACK_USER / SPACETRACK_PASS).{RS}")
    elif st_state and st_state != "ok":
        print(f" {Y}Space-Track: {st_state}{RS}")
    print()
    print(f" {'NORAD':<7} | {'TARGET':<26} | {'TLE EPOCH':<19} | {'SIGNAL':<13} | {'PACKET HEALTH'}")
    print("-" * 89)
    if not rows:
        print(f" {G}No telemetry yet -- the first scan is {'running' if scanning else 'about to start'}...{RS}")
    colors = {"ONLINE": art.GREEN, "INTERMITTENT": art.GOLD, "OFFLINE": R, "LINK ERROR": R}
    for r in rows:
        color = colors.get(r.get("Status", ""), G)
        ep_color = R if r.get("TLE Stale") else ""
        print(f" {str(r.get('NORAD ID', '')):<7} | {str(r.get('Target Name', ''))[:26]:<26} | "
              f"{ep_color}{str(r.get('TLE Epoch', ''))[:19]:<19}{RS if ep_color else ''} | "
              f"{color}{str(r.get('Status', '')):<13}{RS} | "
              f"{str(r.get('Packet Health', ''))}")
    if error:
        print(f"\n {R}{error}{RS}")
    if msg:
        print(f"\n {C}{msg}{RS}")
    print(f"\n {G}[L] again = rescan now | [B] 3D BlueGlobe dashboard | [V] orbital ops menu (re-entries, sky, NASA/JPL){RS}")
    print(f" {G}Targets are edited in norad_targets.json; packet health = good / (good + bad) SatNOGS observations (24h), "
          f"[95% range]. LOW SAMPLE = under 8 observations; red epoch = TLE older than 14 days; "
          f"* = last known value, SatNOGS unreachable this scan.{RS}")


# ======================================================================== CLI ====
def _install_masking():
    if os.environ.get("HANNIBAL_NO_MASK") == "1":
        return
    try:
        import hannibal_security_bootstrap  # noqa: F401  (installs process-wide redaction on import)
    except Exception:
        pass


def main(argv=None):
    _install_masking()
    if os.name == "nt":
        os.system("")  # enable ANSI colours in the Windows console
    ap = argparse.ArgumentParser(prog="hannibal_orbital", description="Hannibal Orbital Directorate")
    for flag, helptext in (("--scan", "scan SatNOGS and write telemetry_report.json"), ("--sky", "sky over home (Horizons)"),
                           ("--decay", "re-entry watch (Space-Track)"), ("--conjunctions", "close approaches (Space-Track)"),
                           ("--boxscore", "catalogue box score (Space-Track)"), ("--kessler", "debris cascade watch (CelesTrak catalog)"), ("--status", "credentials / masking / cache"),
                           ("--home", "Military + Globalstar overhead now (N2YO)"), ("--moons", "browse asteroid/comet/TNO satellites (JPL sb_sat)"),
                           ("--dashboard", "open the BlueGlobe dashboard"), ("--art", "Soviet space art gallery"), ("--feeder", "ADS-B feeder (asks for confirmation)")):
        ap.add_argument(flag, action="store_true", help=helptext)
    ap.add_argument("--no-anim", action="store_true", help="skip the boot animation")
    ap.add_argument("--sat", metavar="NORAD", type=int, help="N2YO detail for one satellite (position, TLE, passes)")
    ap.add_argument("--neo", metavar="DES", help="where it won't be: impact exclusion for one asteroid/comet (JPL)")
    ap.add_argument("--no-login", action="store_true", help="do not ask for the Space-Track login / N2YO key")
    args = ap.parse_args(argv)

    color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    ask = lambda prompt, default="": (input(prompt).strip() or default)
    one_shots = [("scan", lambda: rt.main()), ("sky", lambda: screen_sky(ask, print, color)),
                 ("home", lambda: screen_home(ask, print, color)), ("moons", lambda: screen_asteroid_moons(ask, print, color)),
                 ("decay", lambda: screen_reentry(ask, print, color)), ("conjunctions", lambda: screen_conjunctions(ask, print, color)),
                 ("boxscore", lambda: screen_boxscore(ask, print, color)), ("kessler", lambda: hannibal_kessler and hannibal_kessler.screen_kessler(ask, print, color)), ("art", lambda: screen_gallery(ask, print, color)), ("status", lambda: screen_status(ask, print, color)),
                 ("dashboard", lambda: print(sat_launch_dashboard()) or time.sleep(0.2)),
                 ("feeder", lambda: screen_feeder(ask, print, color))]
    ran = False
    one_shots.append(("sat", lambda: _satellite_detail(args.sat, print, color)))
    one_shots.append(("neo", lambda: hannibal_neo and print(hannibal_neo.report(args.neo))))
    needs_keys = ("scan", "decay", "conjunctions", "boxscore", "home", "sat", "dashboard")
    if any(getattr(args, n) for n in needs_keys) and not args.no_login:
        # one-shot flags that talk to Space-Track / N2YO: ask once if the login is missing (the menu asks for itself)
        if hannibal_login.ensure_logins(input_fn=input, secret_fn=getpass.getpass, print_fn=print).get("changed"):
            reset_clients()
    for name, fn in one_shots:
        if getattr(args, name):
            ran = True
            if name != "scan":
                print(art.banner("PROJECT HANNIBAL // ORBITAL DIRECTORATE", color=color))
            fn()
    if args.dashboard:  # keep the server alive until Ctrl+C
        try:
            print("\n  Press Ctrl+C to stop the dashboard server.")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    if ran:
        return 0
    try:
        return run_menu(animate=not args.no_anim, logins=not args.no_login)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
