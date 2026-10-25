"""Hourly evidence snapshot for the Apophis study (receive-only, public data only).

    python docs/investigation/apophis/collect.py            # writes evidence/<YYYY-MM-DD_HHMM>/

One snapshot = everything needed to judge criteria C1 to C6 at that moment, with the raw replies:
  * NASA/JPL close approaches, Sentry, Small-Body Database (orbit + non-gravitational terms)
  * ESA NEOCC close approaches (.clolin), risk list, observation file, orbit (.ke1)   (hannibal_crosscheck)
  * NASA/JPL Horizons topocentric table for the point off Lisbon (criterion C4)
Every reply is fetched live (no cache, no stale copy). Every saved file is listed in SHA256SUMS, and
snapshot.json holds the extracted numbers that the study pipeline aggregates. Nothing is interpreted
here beyond the pre-registered criteria. A source that fails is recorded as failed, never filled in.

Exit code: 0 consistent, 2 a source failed (NO DATA somewhere), 3 a pre-registered criterion fired.
"""
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORBITAL = HERE.parents[2] / "orbital"
sys.path.insert(0, str(ORBITAL))

import hannibal_crosscheck as xc          # noqa: E402
import hannibal_neo_where as where        # noqa: E402

EVIDENCE = HERE / "evidence"
CA_UTC = datetime(2029, 4, 13, 21, 45, tzinfo=timezone.utc)
LISBON = where.LISBON_OFFSHORE
P2029_KM, P2029_3SIGMA_KM = 38_011.46, 3.3          # pre-registered C5 baseline (solution 220)
SCHEMA = 1


def lisbon_capture(net):
    start, stop = CA_UTC - timedelta(hours=12), CA_UTC + timedelta(hours=12)
    params = where.horizons_params("99942", start, stop, "1m", site=LISBON)
    when = datetime.now(timezone.utc)
    res = net.request("GET", where.HORIZONS_URL, params=params, expect="text", ttl=0, stale_ok=False, timeout=90)
    rec = {"name": "jpl_horizons_lisbon", "url": where.HORIZONS_URL, "params": params,
           "retrieved_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": res.ok, "error": res.error}
    if res.ok:
        raw = res.data.encode("utf-8")
        rec.update({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "text": res.data})
    return rec


def snapshot(net=None, now=None):
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d_%H%M")
    records = xc.capture("99942", net)
    records["jpl_horizons_lisbon"] = lisbon_capture(net)
    analysis = xc.analyse("99942", records, today=now)

    snap = {"schema": SCHEMA, "stamp": stamp, "taken_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources_ok": {k: bool(v.get("ok")) for k, v in records.items()},
            "crosscheck_verdict": analysis["verdict"], "concerns": analysis.get("concerns", []),
            "notes": analysis.get("notes", []), "criteria": {f"C{i}": None for i in range(1, 7)}}
    jo = analysis.get("jpl_orbit") or {}
    snap.update({"jpl_orbit_id": jo.get("orbit_id"), "jpl_n_obs": jo.get("n_obs_used"), "jpl_last_obs": jo.get("last_obs"),
                 "jpl_sentry": analysis.get("jpl_sentry"), "esa_risk_list": analysis.get("esa_risk_list"),
                 "esa_n_obs": (analysis.get("esa_observations") or {}).get("count"),
                 "esa_last_obs": (analysis.get("esa_observations") or {}).get("last")})
    ng = analysis.get("nongrav") or {}
    for agency in ("jpl", "esa"):
        for term in ("A1", "A2", "A3"):
            v = (ng.get(agency) or {}).get(term)
            snap[f"{agency}_{term}"] = v[0] if v else None
            snap[f"{agency}_{term}_sigma"] = v[1] if v else None
    p29 = next((p for p in analysis.get("passes", []) if str(p.get("date", "")).startswith("2029")), None)
    if p29:
        snap.update({"jpl_2029_km": p29.get("jpl_km"), "esa_2029_km": p29.get("esa_km"),
                     "diff_2029_km": p29.get("diff_km"), "nsigma_2029": p29.get("n_sigma"),
                     "jpl_2029_min_km": p29.get("jpl_min_km"), "esa_2029_min_km": p29.get("esa_min_km"),
                     "time_diff_2029_s": p29.get("time_diff_s")})
    lis = records["jpl_horizons_lisbon"]
    if lis.get("ok"):
        try:
            tc = where.target_check(where.parse_horizons(json.loads(lis["text"])), LISBON)
            snap.update({"lisbon_verdict": tc["verdict"], "lisbon_closest_km": tc["closest_km"],
                         "lisbon_nearest_edge_km": tc["nearest_edge_km"], "lisbon_closest_utc": tc["closest_time"]})
        except (ValueError, KeyError) as exc:
            snap.update({"lisbon_verdict": "NO DATA", "lisbon_error": str(exc)})
    else:
        snap.update({"lisbon_verdict": "NO DATA", "lisbon_error": lis.get("error")})

    # pre-registered criteria: True = fired, False = checked and not fired, None = could not be checked
    c = snap["criteria"]
    if analysis["verdict"] != xc.NO_DATA:
        for i in (1, 2, 3, 6):
            c[f"C{i}"] = any(x.startswith(f"C{i}:") for x in analysis.get("concerns", []))
        if not records["jpl_sbdb"].get("ok"):
            c["C6"] = None
    if snap.get("lisbon_verdict") in ("IMPOSSIBLE", "POSSIBLE"):
        c["C4"] = snap["lisbon_verdict"] == "POSSIBLE"
    if snap.get("jpl_2029_km") is not None:
        c["C5"] = abs(snap["jpl_2029_km"] - P2029_KM) > P2029_3SIGMA_KM

    folder = EVIDENCE / stamp
    xc.write_evidence(records, analysis, folder)
    (folder / "snapshot.json").write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    sums = (folder / "SHA256SUMS").read_text(encoding="utf-8")
    sums += f"{hashlib.sha256((folder / 'snapshot.json').read_bytes()).hexdigest()}  snapshot.json\n"
    (folder / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return snap, folder


def main():
    snap, folder = snapshot()
    fired = [k for k, v in snap["criteria"].items() if v]
    unchecked = [k for k, v in snap["criteria"].items() if v is None]
    print(f"{snap['stamp']}  cross-check {snap['crosscheck_verdict']}  2029 JPL {snap.get('jpl_2029_km')} km  "
          f"ESA {snap.get('esa_2029_km')} km  Lisbon {snap.get('lisbon_verdict')}  "
          f"fired {fired or 'none'}  unchecked {unchecked or 'none'}")
    print(folder)
    if fired:
        return 3
    return 2 if unchecked or not all(snap["sources_ok"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
