"""Where it won't be: Earth-impact exclusion for any near-Earth asteroid or comet (receive-only).

    sources  NASA/JPL CNEOS close-approach data   https://ssd-api.jpl.nasa.gov/cad.api
             NASA/JPL Sentry impact monitoring     https://ssd-api.jpl.nasa.gov/sentry.api
             NASA/JPL Small-Body Database          https://ssd-api.jpl.nasa.gov/sbdb.api
    auth     none; every call goes through hannibal_net (rate limited, cached, masked)

For each Earth close approach in the window it reports the nominal distance, JPL's 3-sigma
minimum and maximum distance, the width of that window, and the clearance above the
atmosphere at the nearest edge. A pass is EXCLUDED when even the nearest edge stays above
Earth's equatorial radius plus 100 km.

The overall verdict always defers to Sentry. A single pass can be cleanly excluded while a
later impact is still possible: if the object goes through a keyhole on that pass, Earth's
gravity can set up a collision years afterwards (Bennu's 2135 flyby is the standard case).
Those later possibilities are what Sentry tracks, so:

    Sentry lists the object        -> NOT EXCLUDED, with JPL's impact probability
    Sentry removed / never listed  -> EXCLUDED if every pass in the window clears the atmosphere

    python hannibal_neo.py 99942              # Apophis
    python hannibal_neo.py 101955 --json bennu.json
"""
import argparse
import json
import sys
from datetime import date

AU_KM = 149_597_870.7
EARTH_EQ_RADIUS_KM = 6_378.137
ATMOSPHERE_KM = 100.0          # Karman line
LUNAR_DISTANCE_KM = 384_400.0
GEO_RADIUS_KM = 42_164.0       # geostationary orbit, from Earth's centre

CAD_URL = "https://ssd-api.jpl.nasa.gov/cad.api"
SENTRY_URL = "https://ssd-api.jpl.nasa.gov/sentry.api"
SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb.api"
TTL = 6 * 3600
DEFAULT_END = "2200-01-01"     # CNEOS publishes close approaches up to 2200
DEFAULT_DIST_MAX_AU = 0.05     # about 19.5 lunar distances

EXCLUDED, NOT_EXCLUDED, NO_DATA = "EXCLUDED", "NOT EXCLUDED", "NO DATA"


# ------------------------------------------------------------------ analysis ----
def approaches_from_cad(payload, des=None):
    """CAD JSON -> list of approach dicts. Raises ValueError if a row belongs to another object."""
    fields = payload.get("fields") or []
    idx = {f: i for i, f in enumerate(fields)}
    out = []
    for row in payload.get("data") or []:
        if des is not None and str(row[idx["des"]]).strip() != str(des).strip():
            raise ValueError(f"close-approach data returned another object ({row[idx['des']]})")
        out.append(assess_pass(row[idx["cd"]], float(row[idx["dist"]]), float(row[idx["dist_min"]]),
                               float(row[idx["dist_max"]]), float(row[idx["v_rel"]]),
                               row[idx["t_sigma_f"]] if "t_sigma_f" in idx else ""))
    return out


def assess_pass(when, dist_au, dist_min_au, dist_max_au, v_rel_kms, t_sigma=""):
    d, lo, hi = dist_au * AU_KM, dist_min_au * AU_KM, dist_max_au * AU_KM
    floor = EARTH_EQ_RADIUS_KM + ATMOSPHERE_KM
    window = hi - lo
    clearance = lo - floor
    return {
        "date": when, "distance_km": d, "min_km": lo, "max_km": hi, "window_km": window,
        "v_rel_kms": v_rel_kms, "time_uncertainty": t_sigma,
        "clearance_above_atmosphere_km": clearance,
        "margin_ratio": (clearance / window) if window > 0 else float("inf"),
        "lunar_distances": d / LUNAR_DISTANCE_KM,
        "inside_geo": d < GEO_RADIUS_KM,
        # a 3-sigma window wider than the distance itself means the linear estimate is only a rough guide
        "rough": window > d,
        "verdict": EXCLUDED if clearance > 0 else NOT_EXCLUDED,
    }


def sentry_status(payload):
    """Sentry JSON -> {'state': listed|removed|not_listed|unknown, ...}."""
    if not isinstance(payload, dict):
        return {"state": "unknown"}
    if payload.get("removed"):
        return {"state": "removed", "removed": payload["removed"]}
    summary = payload.get("summary")
    if summary:
        data = payload.get("data") or []
        first = min((r.get("date", "") for r in data), default="")
        return {"state": "listed", "ip": float(summary.get("ip") or 0), "ps_cum": summary.get("ps_cum"),
                "ts_max": summary.get("ts_max"), "n_imp": int(summary.get("n_imp") or len(data)),
                "first_date": first[:4], "last_date": max((r.get("date", "") for r in data), default="")[:4],
                "method": summary.get("method"), "fullname": summary.get("fullname")}
    if "not found" in str(payload.get("error", "")).lower():
        return {"state": "not_listed"}
    return {"state": "unknown", "error": payload.get("error", "")}


def orbit_quality(sbdb):
    o = (sbdb or {}).get("orbit") or {}
    obj = (sbdb or {}).get("object") or {}
    phys = {p.get("name"): p.get("value") for p in (sbdb or {}).get("phys_par") or []}
    return {"name": obj.get("fullname"), "orbit_id": o.get("orbit_id"), "condition_code": o.get("condition_code"),
            "data_arc_days": o.get("data_arc"), "n_obs": o.get("n_obs_used"), "last_obs": o.get("last_obs"),
            "diameter_km": phys.get("diameter"), "H": phys.get("H")}


def overall(passes, sentry):
    if sentry.get("state") == "listed":
        if not sentry.get("ip"):
            return NOT_EXCLUDED, "JPL Sentry still lists this object."
        return NOT_EXCLUDED, (f"JPL Sentry lists {sentry['n_imp']} possible impacts "
                              f"({sentry['first_date']}-{sentry['last_date']}), cumulative probability "
                              f"{sentry['ip']:.2g} (about 1 in {round(1 / sentry['ip']):,}).")
    if not passes:
        if sentry.get("state") in ("removed", "not_listed"):
            return EXCLUDED, "No close approach inside the window and no Sentry impact solutions."
        return NO_DATA, "No close-approach data and no Sentry answer."
    bad = [p for p in passes if p["verdict"] != EXCLUDED]
    if bad:
        return NOT_EXCLUDED, f"{len(bad)} pass(es) whose uncertainty window reaches the atmosphere."
    if sentry.get("state") == "unknown":
        return NO_DATA, "Every pass clears Earth, but Sentry could not be reached to rule out later impacts."
    why = "removed from" if sentry["state"] == "removed" else "never on"
    return EXCLUDED, f"Every pass clears the atmosphere and the object is {why} JPL's Sentry risk list."


# ------------------------------------------------------------------ fetching ----
def _jpl_error(payload):
    if isinstance(payload, dict) and payload.get("code") not in (None, "200", 200):
        return payload.get("message") or f"JPL error {payload.get('code')}"
    return ""


def fetch(des, net=None, end=DEFAULT_END, dist_max_au=DEFAULT_DIST_MAX_AU, start=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    start = start or date.today().isoformat()
    cad = net.get_json(CAD_URL, params={"des": des, "date-min": start, "date-max": end,
                                        "dist-max": str(dist_max_au)}, ttl=TTL, validate=_jpl_error)
    sentry = net.get_json(SENTRY_URL, params={"des": des}, ttl=TTL)
    sbdb = net.get_json(SBDB_URL, params={"sstr": des, "phys-par": "true"}, ttl=TTL, validate=_jpl_error)
    return cad, sentry, sbdb


def analyse(des, cad_payload, sentry_payload, sbdb_payload, start=None, end=DEFAULT_END,
            dist_max_au=DEFAULT_DIST_MAX_AU):
    passes = approaches_from_cad(cad_payload or {}, des) if cad_payload else []
    sentry = sentry_status(sentry_payload)
    verdict, reason = overall(passes, sentry)
    return {"designation": des, "window": [start or date.today().isoformat(), end], "dist_max_au": dist_max_au,
            "orbit": orbit_quality(sbdb_payload), "sentry": sentry, "passes": passes,
            "verdict": verdict, "reason": reason}


def run(des, net=None, end=DEFAULT_END, dist_max_au=DEFAULT_DIST_MAX_AU):
    cad, sentry, sbdb = fetch(des, net, end, dist_max_au)
    if not cad.ok and str(cad.error).startswith("HTTP 400"):
        return None, f"JPL does not recognise '{des}' (try the number, e.g. 99942, or a designation like '2024 YR4')"
    if not cad.ok and not sentry.ok:
        return None, f"JPL unavailable: {cad.error or sentry.error}"
    result = analyse(des, cad.data if cad.ok else None, sentry.data if sentry.ok else {"error": sentry.error},
                     sbdb.data if sbdb.ok else None, end=end, dist_max_au=dist_max_au)
    if not cad.ok:
        result["verdict"], result["reason"] = NO_DATA, f"close-approach data unavailable ({cad.error})"
    return result, ""


# ------------------------------------------------------------------ report ------
def format_report(r):
    o = r["orbit"]
    lines = [f"  WHERE IT WON'T BE  {o.get('name') or r['designation']}",
             f"  Window {r['window'][0]} to {r['window'][1]}, passes within "
             f"{r.get('dist_max_au', DEFAULT_DIST_MAX_AU)} au"]
    if o.get("orbit_id"):
        lines.append(f"  Orbit {o['orbit_id']}: condition code U={o.get('condition_code')} (0 best, 9 worst), "
                     f"{o.get('n_obs')} observations over {o.get('data_arc_days')} days, last {o.get('last_obs')}")
    s = r["sentry"]
    lines.append("  Sentry: " + {"listed": "ON THE RISK LIST", "removed": f"removed {s.get('removed', '')}",
                                 "not_listed": "never listed"}.get(s["state"], "no answer"))
    lines += ["", f"  {'date (UTC)':<18} {'distance km':>13} {'nearest edge':>13} {'window km':>11} "
                  f"{'above atmos.':>13}  this pass"]
    for p in r["passes"]:
        tag = p["verdict"] + (" (inside GEO)" if p["inside_geo"] else "") + (" ~rough" if p["rough"] else "")
        lines.append(f"  {p['date']:<18} {p['distance_km']:>13,.0f} {p['min_km']:>13,.0f} {p['window_km']:>11,.1f} "
                     f"{p['clearance_above_atmosphere_km']:>13,.0f}  {tag}")
    if not r["passes"]:
        lines.append("  (no Earth close approaches inside the window)")
    lines += ["", f"  VERDICT: {r['verdict']}. {r['reason']}"]
    if r["sentry"]["state"] == "listed" and r["passes"] and all(p["verdict"] == EXCLUDED for p in r["passes"]):
        lines.append("  Every listed pass clears Earth, but a pass can steer the object through a keyhole toward a")
        lines.append("  later impact. Sentry's impact solutions cover that case, so its verdict stands.")
    lines.append("  Distances are JPL's 3-sigma bounds from linearised orbit uncertainty. ~rough = the window is wider")
    lines.append("  than the distance itself, so that row is only a rough guide; Sentry decides those cases.")
    return "\n".join(lines)


def report(des, **kw):
    """Report text for one object, or the error line if JPL could not be reached."""
    result, err = run(des, **kw)
    return f"  [!] {err}" if err else format_report(result)


def screen_neo(ask, print_fn, color=False):
    """[W] screen for the Orbital Ops menu."""
    des = ask("  Asteroid or comet (number or designation) [99942 Apophis]: ", "99942").strip() or "99942"
    print_fn("  Asking NASA/JPL (close approaches, Sentry, orbit)...")
    print_fn(report(des))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Where it won't be: Earth-impact exclusion for a small body (NASA/JPL)")
    ap.add_argument("des", nargs="?", default="99942", help="number or designation, e.g. 99942 or '2024 YR4'")
    ap.add_argument("--until", default=DEFAULT_END, help="end of the window, YYYY-MM-DD (JPL data stops near 2200)")
    ap.add_argument("--dist-max", type=float, default=DEFAULT_DIST_MAX_AU, help="largest approach distance, au")
    ap.add_argument("--json", help="also write the result to this file")
    args = ap.parse_args(argv)
    result, err = run(args.des, end=args.until, dist_max_au=args.dist_max)
    if err:
        print(err, file=sys.stderr)
        return 1
    print(format_report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    return 0 if result["verdict"] != NO_DATA else 2


if __name__ == "__main__":
    sys.exit(main())
