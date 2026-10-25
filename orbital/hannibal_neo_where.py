"""Where it will be: the other half of [W] "Where it won't be" (receive-only).

    source   NASA/JPL Horizons (observer tables with 3-sigma covariance)  https://ssd.jpl.nasa.gov/api/horizons.api
    auth     none; every call goes through hannibal_net (rate limited, cached, masked)

Three answers for one asteroid or comet:

  TRACK     minute by minute around the closest pass: geocentric distance, the point on Earth it is
            straight overhead of (sub-point), brightness, and the 3-sigma box it must be inside
            (along x across the sky, and +/- along the line of sight), all in km.
  ENVELOPE  the same 3-sigma box at every Earth close approach in the window, so you can see how
            the certainty grows from a few km to millions of km over the decades.
  TARGET    the impossible-event test for one point on Earth (default: the Atlantic off Lisbon).
            Over the window it finds the closest the object comes to that point and the nearest
            3-sigma edge. An impact there needs that edge to reach the ground; if it stays above the
            atmosphere, the impact at that point is IMPOSSIBLE on JPL's own uncertainty, and Sentry
            (via hannibal_neo) covers any later keyhole return.

    python hannibal_neo_where.py 99942
    python hannibal_neo_where.py 99942 --target 38.70 -9.60 "Off Lisbon" --json where.json

Sub-point longitudes use Greenwich apparent sidereal time computed here from UTC (UT1-UTC < 0.9 s,
so up to about 0.004 deg of longitude, ~0.4 km on the ground). Horizons' 3-sigma figures are its
linearised covariance, the same basis as the "Where it won't be" windows.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone

AU_KM = 149_597_870.7
EARTH_EQ_RADIUS_KM = 6_378.137
ATMOSPHERE_KM = 100.0
ARCSEC = math.pi / 648_000.0

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
TTL = 6 * 3600
LISBON_OFFSHORE = (38.70, -9.60, "Atlantic off Lisbon")
TRACK_HALF_SPAN_MIN = 180
TARGET_HALF_SPAN_MIN = 720

POSSIBLE, IMPOSSIBLE, NO_DATA = "POSSIBLE", "IMPOSSIBLE", "NO DATA"
CAD_FMT = "%Y-%b-%d %H:%M"


# ------------------------------------------------------------------ geometry ----
def julian_date(t):
    t = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
    return t.timestamp() / 86400.0 + 2440587.5


def gast_deg(t):
    """Greenwich apparent sidereal time (deg) for a UTC datetime; IAU 1982 GMST + main nutation terms."""
    jd = julian_date(t)
    d = jd - 2451545.0
    T = d / 36525.0
    gmst = 280.46061837 + 360.98564736629 * d + 0.000387933 * T * T - T ** 3 / 38_710_000.0
    om = math.radians(125.04452 - 1934.136261 * T)
    L = math.radians(280.4665 + 36000.7698 * T)
    Lm = math.radians(218.3165 + 481267.8813 * T)
    dpsi = (-17.20 * math.sin(om) - 1.32 * math.sin(2 * L) - 0.23 * math.sin(2 * Lm)
            + 0.21 * math.sin(2 * om)) / 3600.0
    eps = math.radians(23.4393 - 0.0130 * T)
    return (gmst + dpsi * math.cos(eps)) % 360.0


def sub_point(ra_deg, dec_deg, t):
    """Surface point on the line from Earth's centre to the object: (geodetic lat, lon east-positive, -180..180).

    At 38,000 km the local vertical there points within ~0.2 deg of the object (checked against Horizons)."""
    lon = (ra_deg - gast_deg(t) + 180.0) % 360.0 - 180.0
    lat = math.degrees(math.atan2(math.tan(math.radians(dec_deg)), 1 - 0.00669438))   # geocentric -> geodetic
    return lat, lon


def box_km(row):
    """3-sigma box from a Horizons row: along/across the sky (full width) and +/- range, km."""
    d = row["delta_km"]
    return {"along_km": 2 * row["smaa_arcsec"] * ARCSEC * d, "across_km": 2 * row["smia_arcsec"] * ARCSEC * d,
            "range_pm_km": row["rng3_km"]}


# ------------------------------------------------------------------ parsing -----
def _num(s):
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_horizons(payload):
    """Horizons JSON (CSV_FORMAT=YES) -> list of row dicts. Raises ValueError on an error or empty table."""
    text = (payload or {}).get("result") or ""
    if "$$SOE" not in text:
        msg = (payload or {}).get("error") or next((ln.strip() for ln in text.splitlines()
                                                    if "No matches" in ln or "ERROR" in ln.upper()), "")
        raise ValueError(msg or "Horizons returned no ephemeris table")
    head, body = text.split("$$SOE", 1)
    body = body.split("$$EOE", 1)[0]
    header = [ln for ln in head.splitlines() if "Date__(UT)" in ln][-1]
    cols = [c.strip() for c in header.split(",")]
    idx = {c: i for i, c in enumerate(cols) if c}

    def pick(cells, *names):
        for n in names:
            if n in idx and idx[n] < len(cells):
                return _num(cells[idx[n]])
        return None

    if "delta" not in idx or not any(k in idx for k in ("R.A.__(a-app)", "R.A._(a-app)")):
        raise ValueError("Horizons table is missing the distance or position columns")
    rows = []
    for ln in body.strip().splitlines():
        cells = ln.split(",")
        when = datetime.strptime(cells[0].strip(), CAD_FMT).replace(tzinfo=timezone.utc)
        delta = pick(cells, "delta")
        rows.append({
            "time": when, "sun": cells[1].strip() if len(cells) > 1 else "", "ra_deg": pick(cells, "R.A.__(a-app)", "R.A._(a-app)"),
            "dec_deg": pick(cells, "DEC___(a-app)", "DEC_(a-app)"),
            "az_deg": pick(cells, "Azimuth_(a-app)", "Azi_(a-app)"),
            "el_deg": pick(cells, "Elevation_(a-app)", "Elev_(a-app)"),
            "mag": pick(cells, "APmag", "T-mag"),
            "delta_km": delta * AU_KM if delta is not None else None,
            "smaa_arcsec": pick(cells, "SMAA_3sig") or 0.0, "smia_arcsec": pick(cells, "SMIA_3sig") or 0.0,
            "rng3_km": pick(cells, "RNG_3sigma") or 0.0,
        })
    if not rows:
        raise ValueError("Horizons returned an empty table")
    return rows


# ------------------------------------------------------------------ fetching ----
def _horizons_error(payload):
    if not isinstance(payload, dict):
        return "Horizons: unexpected reply"
    if payload.get("error"):
        return f"Horizons: {payload['error']}"
    return "" if "$$SOE" in (payload.get("result") or "") else "Horizons returned no ephemeris table"


def _command(des):
    s = str(des).strip()
    return f"'{s};'" if s.isdigit() else f"'DES={s};'"


def horizons_params(des, start, stop, step="1m", site=None):
    p = {"format": "json", "COMMAND": _command(des), "OBJ_DATA": "NO", "MAKE_EPHEM": "YES",
         "EPHEM_TYPE": "OBSERVER", "START_TIME": f"'{start:%Y-%m-%d %H:%M}'",
         "STOP_TIME": f"'{stop:%Y-%m-%d %H:%M}'", "STEP_SIZE": f"'{step}'", "CSV_FORMAT": "YES",
         "ANG_FORMAT": "DEG", "TIME_DIGITS": "MINUTES", "EXTRA_PREC": "YES"}
    if site is None:
        p.update({"CENTER": "'500@399'", "QUANTITIES": "'2,9,20,37,39'"})
    else:
        lat, lon = site[0], site[1]
        p.update({"CENTER": "'coord@399'", "COORD_TYPE": "GEODETIC",
                  "SITE_COORD": f"'{lon % 360.0:.5f},{lat:.5f},0'", "QUANTITIES": "'2,4,9,20,37,39'"})
    return p


def fetch_rows(des, start, stop, step="1m", site=None, net=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    res = net.get_json(HORIZONS_URL, params=horizons_params(des, start, stop, step, site), ttl=TTL,
                       validate=_horizons_error)
    if not res.ok:
        return None, res.error or "Horizons unavailable"
    try:
        return parse_horizons(res.data), ""
    except ValueError as exc:
        return None, str(exc)


# ------------------------------------------------------------------ analysis ----
def track(rows):
    out = []
    for r in rows:
        lat, lon = sub_point(r["ra_deg"], r["dec_deg"], r["time"])
        out.append({"time": r["time"].strftime(CAD_FMT), "distance_km": r["delta_km"],
                    "altitude_km": r["delta_km"] - EARTH_EQ_RADIUS_KM, "sub_lat": lat, "sub_lon": lon,
                    "mag": r["mag"], **box_km(r)})
    return out


def target_check(rows, target):
    """Impossible-event test for one surface point. rows = topocentric Horizons rows at that point."""
    lat, lon, name = target
    best = min(rows, key=lambda r: r["delta_km"])
    edge = min(r["delta_km"] - r["rng3_km"] for r in rows)
    clearance = edge - ATMOSPHERE_KM
    up = [r for r in rows if (r["el_deg"] or -90) > 0]
    dark = [r for r in up if r.get("sun") not in ("*", "C")]      # Horizons: * daylight, C civil twilight
    return {"name": name, "lat": lat, "lon": lon,
            "closest_time": best["time"].strftime(CAD_FMT), "closest_km": best["delta_km"],
            "closest_elevation_deg": best["el_deg"], "nearest_edge_km": edge,
            "clearance_above_atmosphere_km": clearance,
            "visible_from": up[0]["time"].strftime(CAD_FMT) if up else None,
            "visible_until": up[-1]["time"].strftime(CAD_FMT) if up else None,
            "max_elevation_deg": max((r["el_deg"] for r in up), default=None),
            "dark_from": dark[0]["time"].strftime(CAD_FMT) if dark else None,
            "dark_until": dark[-1]["time"].strftime(CAD_FMT) if dark else None,
            "brightest_mag": min((r["mag"] for r in dark if r["mag"] is not None), default=None),
            "verdict": IMPOSSIBLE if clearance > 0 else POSSIBLE}


def envelope_row(cad_pass, rows):
    r = min(rows, key=lambda x: abs((x["time"] - _cad_time(cad_pass["date"])).total_seconds()))
    return {"date": cad_pass["date"], "distance_km": cad_pass["distance_km"],
            "time_uncertainty": cad_pass.get("time_uncertainty", ""), "rough": cad_pass.get("rough", False),
            **box_km(r)}


def _cad_time(s):
    return datetime.strptime(s, CAD_FMT).replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ run ---------
def run(des="99942", target=LISBON_OFFSHORE, net=None, passes=None, sentry=None):
    """passes/sentry: from hannibal_neo.run(); fetched here when not given."""
    if passes is None:
        import hannibal_neo
        neo, err = hannibal_neo.run(des, net=net)
        if err:
            return None, err
        passes, sentry = neo["passes"], neo["sentry"]
    if not passes:
        return None, "no Earth close approach in the window, so there is no flyby to track"
    first = min(passes, key=lambda p: p["distance_km"])
    t0 = _cad_time(first["date"])
    rows, err = fetch_rows(des, t0 - timedelta(minutes=TRACK_HALF_SPAN_MIN),
                           t0 + timedelta(minutes=TRACK_HALF_SPAN_MIN), "1m", net=net)
    if err:
        return None, f"JPL Horizons unavailable: {err}"
    result = {"designation": des, "closest_pass": first["date"], "sentry": sentry, "track": track(rows)}

    env = []
    for p in passes:
        t = _cad_time(p["date"])
        prow, perr = (rows, "") if p is first else fetch_rows(des, t - timedelta(minutes=1),
                                                              t + timedelta(minutes=1), "1m", net=net)
        env.append(envelope_row(p, prow) if prow else {"date": p["date"], "distance_km": p["distance_km"],
                                                        "error": perr})
    result["envelope"] = env

    if target:
        trows, terr = fetch_rows(des, t0 - timedelta(minutes=TARGET_HALF_SPAN_MIN),
                                 t0 + timedelta(minutes=TARGET_HALF_SPAN_MIN), "1m", site=target, net=net)
        if terr:
            result["target"] = {"name": target[2], "verdict": NO_DATA, "error": terr}
        else:
            tc = target_check(trows, target)
            if (sentry or {}).get("state") == "listed":
                tc["note"] = "Sentry still lists this object: a later keyhole return is not ruled out."
            elif (sentry or {}).get("state") not in ("removed", "not_listed"):
                tc["note"] = "Sentry could not be reached: only this flyby is ruled out."
            result["target"] = tc
    return result, ""


# ------------------------------------------------------------------ report ------
def _fmt_km(x):
    return f"{x:,.1f}" if x < 100 else f"{x:,.0f}"


def format_report(r):
    tr = r["track"]
    ca = min(tr, key=lambda x: x["distance_km"])
    lines = [f"  WHERE IT WILL BE  {r['designation']}   closest pass {r['closest_pass']} UTC", "",
             f"  Closest at {ca['time']} UTC: {ca['distance_km']:,.0f} km from Earth's centre, "
             f"{ca['altitude_km']:,.0f} km above the surface,",
             f"  straight overhead of {ca['sub_lat']:.2f}N {ca['sub_lon']:.2f}E"
             f" (3-sigma box {_fmt_km(ca['along_km'])} x {_fmt_km(ca['across_km'])} km, +/-{_fmt_km(ca['range_pm_km'])} km in range)",
             "", f"  {'time (UTC)':<18} {'distance km':>12} {'overhead of':>17} {'mag':>5} {'3-sigma box km':>22}"]
    step = max(1, len(tr) // 24)
    shown = tr[::step]
    if ca not in shown:
        shown = sorted(shown + [ca], key=lambda x: x["time"])
    for x in shown:
        mark = "  <- closest" if x is ca else ""
        mag = f"{x['mag']:.1f}" if x["mag"] is not None else "  -"
        lines.append(f"  {x['time']:<18} {x['distance_km']:>12,.0f} {x['sub_lat']:>7.2f}N {x['sub_lon']:>7.2f}E "
                     f"{mag:>5} {_fmt_km(x['along_km']):>8} x {_fmt_km(x['across_km']):>6} +/-{_fmt_km(x['range_pm_km'])}{mark}")
    lines += ["", "  ENVELOPE (3-sigma box at each pass)", f"  {'date (TDB)':<18} {'distance km':>13} "
              f"{'along x across km':>24} {'+/- range km':>14}  time +/-"]
    for e in r["envelope"]:
        if "error" in e:
            lines.append(f"  {e['date']:<18} {e['distance_km']:>13,.0f}  (Horizons: {e['error']})")
            continue
        lines.append(f"  {e['date']:<18} {e['distance_km']:>13,.0f} {_fmt_km(e['along_km']):>11} x "
                     f"{_fmt_km(e['across_km']):>10} {_fmt_km(e['range_pm_km']):>14}  {e['time_uncertainty']}"
                     + ("  ~rough" if e.get("rough") else ""))
    t = r.get("target")
    if t:
        lines += ["", f"  IMPOSSIBLE-EVENT TEST: impact at {t['name']}"
                  + (f" ({t['lat']:.2f}N {t['lon']:.2f}E)" if "lat" in t else "")]
        if t["verdict"] == NO_DATA:
            lines.append(f"  NO DATA: {t.get('error')}. No conclusion drawn.")
        else:
            lines.append(f"  Closest to that point: {t['closest_km']:,.0f} km at {t['closest_time']} UTC; "
                         f"nearest 3-sigma edge {t['nearest_edge_km']:,.0f} km,")
            lines.append(f"  {t['clearance_above_atmosphere_km']:,.0f} km above the atmosphere. "
                         f"VERDICT: {t['verdict']}.")
            if t.get("visible_from"):
                lines.append(f"  Above the horizon there {t['visible_from']} to {t['visible_until']} UTC, highest "
                             f"{t['max_elevation_deg']:.0f} deg.")
            if t.get("dark_from"):
                lines.append(f"  Up in a dark sky (Sun below civil twilight) {t['dark_from']} to {t['dark_until']} UTC, "
                             f"brightest mag {t['brightest_mag']:.1f} (naked eye: brighter than about 6).")
            if t.get("note"):
                lines.append(f"  {t['note']}")
    lines.append("  Track times are UTC; envelope dates are JPL close-approach times in TDB (about 69 s ahead of UTC).")
    lines.append("  3-sigma boxes are JPL Horizons' linearised covariance; ~rough = see Where it won't be.")
    return "\n".join(lines)


def _json_default(o):
    return o.isoformat() if isinstance(o, datetime) else str(o)


def report(des="99942", **kw):
    """Report text, or the error line if JPL could not be reached."""
    result, err = run(des, **kw)
    return f"  [!] {err}" if err else format_report(result)


def screen_where(ask, print_fn, color=False):
    """Menu screen: track, envelope and the off-Lisbon impossible-event test."""
    des = ask("  Asteroid or comet [99942 Apophis]: ", "99942").strip() or "99942"
    print_fn("  Asking NASA/JPL (close approaches, Sentry, Horizons track)...")
    result, err = run(des)
    print_fn(f"  [!] {err}" if err else format_report(result))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Where it will be: flyby track, 3-sigma envelope and "
                                             "impossible-event test (NASA/JPL Horizons)")
    ap.add_argument("des", nargs="?", default="99942")
    ap.add_argument("--target", nargs=3, metavar=("LAT", "LON", "NAME"),
                    help="surface point for the impossible-event test (default: Atlantic off Lisbon)")
    ap.add_argument("--no-target", action="store_true", help="skip the impossible-event test")
    ap.add_argument("--json", help="also write the result to this file")
    args = ap.parse_args(argv)
    target = None if args.no_target else (
        (float(args.target[0]), float(args.target[1]), args.target[2]) if args.target else LISBON_OFFSHORE)
    result, err = run(args.des, target=target)
    if err:
        print(err, file=sys.stderr)
        return 1
    print(format_report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=_json_default)
    t = result.get("target") or {}
    return 2 if t.get("verdict") == NO_DATA else 0


if __name__ == "__main__":
    sys.exit(main())
