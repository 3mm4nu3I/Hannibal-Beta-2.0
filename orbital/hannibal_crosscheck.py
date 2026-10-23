"""Independent cross-check for one near-Earth object: NASA/JPL versus ESA NEOCC, with an evidence trail.

    sources  NASA/JPL CNEOS close approaches, Sentry, Small-Body Database   https://ssd-api.jpl.nasa.gov
             ESA NEO Coordination Centre: close approaches (.clolin), risk list, observations (.rwo)
                                                                       https://neo.ssa.esa.int/PSDB-portlet/download
    auth     none; receive-only; every call goes through hannibal_net, LIVE (no cache, no stale copy)

JPL and ESA fit their own orbits to the observations with their own software. If both say the same
thing within their stated uncertainties, that is far stronger evidence than one source asked twice.

What it decides, for each close approach both agencies list (matched within 5 days):
    AGREE      the two nominal distances differ by less than 3 combined sigma
    DISAGREE   they differ by more -> that pass needs a human look
And independently, from ESA alone: is any pass's minimum possible distance inside Earth + 100 km,
and is the object on ESA's risk list?

Evidence: every raw reply is hashed (SHA-256) with its URL and retrieval time. Small replies are saved
verbatim; the big ones (ESA risk list, observation file) are kept as hash + the lines that matter, so
anyone can re-download and check. JPL's times are TDB, ESA's .clolin times are UTC (69.184 s apart).

    python hannibal_crosscheck.py 99942
    python hannibal_crosscheck.py 99942 --evidence DIR      # also write the evidence folder
"""
import argparse
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

AU_KM = 149_597_870.7
EARTH_EQ_RADIUS_KM = 6_378.137
ATMOSPHERE_KM = 100.0
TT_MINUS_UTC_S = 69.184            # 32.184 s + 37 leap seconds (none announced since 2017)
MATCH_DAYS = 5
SIGMAS = 3.0

CAD_URL = "https://ssd-api.jpl.nasa.gov/cad.api"
SENTRY_URL = "https://ssd-api.jpl.nasa.gov/sentry.api"
SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb.api"
ESA_URL = "https://neo.ssa.esa.int/PSDB-portlet/download"
SMALL_BYTES = 200_000              # replies up to this size are saved verbatim
# Pre-registered baseline for criterion C6 (docs/investigation/apophis/PREREGISTRATION.md, hypothesis H-A):
# JPL solution 220's transverse non-gravitational acceleration (the Yarkovsky push) and its 1-sigma, au/d^2.
A2_BASELINE, A2_BASELINE_SIGMA = -2.901766637153165e-14, 1.859e-16

AGREE, DISAGREE, ONLY_JPL, ONLY_ESA = "AGREE", "DISAGREE", "JPL only", "ESA only"
CONSISTENT, CONCERN, NO_DATA = "CONSISTENT", "CONCERN", "NO DATA"


# ------------------------------------------------------------------ capture -----
def sources(des, start=None, end="2200-01-01"):
    start = start or date.today().isoformat()
    d = str(des).strip()
    return [
        ("jpl_cad", CAD_URL, {"des": d, "date-min": start, "date-max": end, "dist-max": "0.2"}),
        ("jpl_sentry", SENTRY_URL, {"des": d}),
        ("jpl_sbdb", SBDB_URL, {"sstr": d, "full-prec": "true"}),
        ("esa_clolin", ESA_URL, {"file": f"{d.replace(' ', '')}.clolin"}),
        ("esa_risk_list", ESA_URL, {"file": "esa_risk_list"}),
        ("esa_observations", ESA_URL, {"file": f"{d.replace(' ', '')}.rwo"}),
        ("esa_orbit", ESA_URL, {"file": f"{d.replace(' ', '')}.ke1"}),
    ]


def capture(des, net=None, start=None):
    """Fetch every source live. Returns {name: record}; record['text'] holds the raw reply."""
    if net is None:
        from hannibal_net import default_net
        net = default_net()
    out = {}
    for name, url, params in sources(des, start):
        when = datetime.now(timezone.utc)
        res = net.request("GET", url, params=params, expect="text", ttl=0, stale_ok=False, timeout=60)
        rec = {"name": name, "url": url, "params": params, "retrieved_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "ok": res.ok, "error": res.error}
        if res.ok:
            raw = res.data.encode("utf-8")
            rec.update({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "text": res.data})
        out[name] = rec
    return out


# ------------------------------------------------------------------ parsing -----
def parse_clolin(text):
    """ESA .clolin -> Earth approaches [{time_utc, distance_km, min_km, sigma_km, time_sigma_d}]."""
    rows = []
    for ln in (text or "").splitlines():
        parts = ln.split()
        if len(parts) < 7 or parts[0] != "EARTH":
            continue
        y, m, frac = parts[1].split("/")
        day = float(frac)
        t = datetime(int(y), int(m), int(day), tzinfo=timezone.utc) + timedelta(days=day - int(day))
        rows.append({"time_utc": t, "distance_km": float(parts[4]) * AU_KM, "min_km": float(parts[5]) * AU_KM,
                     "sigma_km": float(parts[6]) * AU_KM, "time_sigma_d": float(parts[3])})
    return rows


def risk_list_lines(text, des):
    """Rows of the ESA risk list whose first column (number or packed designation) is this object."""
    key = str(des).replace(" ", "").lower()
    out = []
    for ln in (text or "").splitlines():
        if "|" not in ln:
            continue
        first = ln.split("|")[0].split()
        if first and first[0].lower() == key:
            out.append(ln)
    return out


def observations_summary(text):
    """ESA .rwo -> counts. One satellite observation spans two lines (S then s): counted once."""
    dates, radar, optical, space = [], 0, 0, 0
    for ln in (text or "").splitlines():
        m = re.match(r"\s*\S+\s+([ORVS])\s+(\S)\s+.*?(\d{4}) (\d\d) (\d\d)", ln)
        if not m or ln.lstrip().startswith("!"):
            continue
        kind = m.group(1)
        if kind == "S" and m.group(2) == "s":      # second line of a space-based observation
            continue
        radar += kind in "RV"
        optical += kind == "O"
        space += kind == "S"
        dates.append(f"{m.group(3)}-{m.group(4)}-{m.group(5)}")
    return {"count": len(dates), "optical": optical, "from_space": space, "radar": radar,
            "first": min(dates) if dates else None, "last": max(dates) if dates else None}


def jpl_nongrav(sbdb_json):
    """SBDB orbit.model_pars -> {'A1': (value, sigma), 'A2': ..., 'A3': ...} for the estimated terms."""
    out = {}
    for p in ((sbdb_json or {}).get("orbit") or {}).get("model_pars") or []:
        if p.get("name") in ("A1", "A2", "A3") and p.get("kind") == "EST":
            out[p["name"]] = (float(p["value"]), float(p["sigma"]) if p.get("sigma") else None)
    return out


def esa_nongrav(ke1_text):
    """ESA .ke1 -> Yarkovsky A2 (au/d^2) and its 1-sigma, from the NGR line and the last RMS value."""
    a2 = sig = None
    for ln in (ke1_text or "").splitlines():
        parts = ln.split()
        if parts[:1] == ["NGR"] and len(parts) >= 3:
            a2 = float(parts[2]) * 1e-10
        if parts[:2] == ["!", "RMS"] and len(parts) >= 9:
            sig = float(parts[-1]) * 1e-10
    return {"A2": (a2, sig)} if a2 is not None else {}


def nongrav_checks(jpl_ng, esa_ng):
    """Criterion C6: a push that the Yarkovsky model of solution 220 does not explain. Returns (concerns, notes)."""
    concerns, notes = [], []
    if not jpl_ng.get("A2"):
        notes.append("JPL publishes no transverse non-gravitational term: C6 not checkable this run")
        return concerns, notes
    a2, s2 = jpl_ng["A2"]
    comb = math.hypot(s2 or 0.0, A2_BASELINE_SIGMA)
    if comb and abs(a2 - A2_BASELINE) > SIGMAS * comb:
        concerns.append(f"C6: JPL Yarkovsky term moved from {A2_BASELINE:.4e} to {a2:.4e} au/d^2 "
                        f"({abs(a2 - A2_BASELINE) / comb:.1f} sigma)")
    for name, what in (("A1", "radial"), ("A3", "out-of-plane")):
        if name in jpl_ng and jpl_ng[name][1]:
            v, s = jpl_ng[name]
            if abs(v) > SIGMAS * s:
                concerns.append(f"C6: JPL now detects a {what} push {name} = {v:.3e} au/d^2 ({abs(v) / s:.1f} sigma)")
    if "A3" in jpl_ng and not jpl_ng["A3"][1]:
        notes.append("JPL added an out-of-plane term A3 without a sigma")
    e = esa_ng.get("A2")
    if e and e[0] is not None:
        ecomb = math.hypot(s2 or 0.0, e[1] or 0.0)
        if ecomb and abs(a2 - e[0]) > SIGMAS * ecomb:
            concerns.append(f"C6: JPL and ESA disagree on the Yarkovsky term ({a2:.4e} vs {e[0]:.4e} au/d^2, "
                            f"{abs(a2 - e[0]) / ecomb:.1f} sigma)")
    return concerns, notes


def jpl_passes(cad_json):
    fields = cad_json.get("fields") or []
    idx = {f: i for i, f in enumerate(fields)}
    out = []
    for r in cad_json.get("data") or []:
        tdb = datetime.strptime(r[idx["cd"]], "%Y-%b-%d %H:%M").replace(tzinfo=timezone.utc)
        lo, hi = float(r[idx["dist_min"]]) * AU_KM, float(r[idx["dist_max"]]) * AU_KM
        out.append({"date_tdb": r[idx["cd"]], "time_utc": tdb - timedelta(seconds=TT_MINUS_UTC_S),
                    "distance_km": float(r[idx["dist"]]) * AU_KM, "min_km": lo, "sigma_km": (hi - lo) / 6.0,
                    "orbit_id": r[idx["orbit_id"]] if "orbit_id" in idx else None})
    return out


# ------------------------------------------------------------------ analysis ----
def compare(jpl, esa):
    rows, used = [], set()
    for j in jpl:
        best = min(((abs((e["time_utc"] - j["time_utc"]).total_seconds()), i, e) for i, e in enumerate(esa)
                    if i not in used), default=None, key=lambda x: x[0])
        window = max(MATCH_DAYS, 3 * esa[best[1]]["time_sigma_d"]) if best else MATCH_DAYS
        if best is None or best[0] > window * 86400:
            rows.append({"date": j["date_tdb"], "status": ONLY_JPL, "jpl_km": j["distance_km"]})
            continue
        _, i, e = best
        used.add(i)
        sigma = math.hypot(j["sigma_km"], e["sigma_km"])
        diff = e["distance_km"] - j["distance_km"]
        rows.append({"date": j["date_tdb"], "jpl_km": j["distance_km"], "esa_km": e["distance_km"],
                     "diff_km": diff, "combined_sigma_km": sigma,
                     "n_sigma": abs(diff) / sigma if sigma > 0 else float("inf"),
                     "time_diff_s": (e["time_utc"] - j["time_utc"]).total_seconds(),
                     "jpl_min_km": j["min_km"], "esa_min_km": e["min_km"],
                     "status": AGREE if sigma > 0 and abs(diff) <= SIGMAS * sigma else DISAGREE})
    jmin = min((j["time_utc"] for j in jpl), default=None)
    for i, e in enumerate(esa):
        if i not in used and (jmin is None or e["time_utc"] >= jmin - timedelta(days=MATCH_DAYS)):
            rows.append({"date": e["time_utc"].strftime("%Y-%b-%d %H:%M") + " UTC", "status": ONLY_ESA,
                         "esa_km": e["distance_km"], "esa_min_km": e["min_km"]})
    return rows


def analyse(des, records, today=None):
    today = today or datetime.now(timezone.utc)
    rec = {k: v for k, v in records.items()}
    out = {"designation": str(des), "checked_utc": today.strftime("%Y-%m-%d %H:%M"), "concerns": [], "notes": []}
    missing = [k for k, v in rec.items() if not v.get("ok")]
    if {"jpl_cad", "esa_clolin"} & set(missing):
        out.update({"verdict": NO_DATA, "reason": "missing " + ", ".join(sorted(missing))})
        return out
    cad = json.loads(rec["jpl_cad"]["text"])
    jpl = jpl_passes(cad)
    esa = [e for e in parse_clolin(rec["esa_clolin"]["text"]) if e["time_utc"] >= today - timedelta(days=1)]
    rows = compare(jpl, esa)
    out["passes"] = rows
    floor = EARTH_EQ_RADIUS_KM + ATMOSPHERE_KM
    for e in esa:
        if e["min_km"] <= floor:
            out["concerns"].append(f"C2: ESA minimum possible distance {e['min_km']:,.0f} km on "
                                   f"{e['time_utc']:%Y-%m-%d} reaches the atmosphere")
    for j in jpl:
        if j["min_km"] <= floor:
            out["concerns"].append(f"C2: JPL minimum possible distance {j['min_km']:,.0f} km on {j['date_tdb']} "
                                   f"reaches the atmosphere")
    for r in rows:
        if r["status"] == DISAGREE:
            # a disagreement on a pass whose window is wider than the distance is expected, not alarming
            rough = r["combined_sigma_km"] * 6 > min(r["jpl_km"], r["esa_km"])
            (out["notes"] if rough else out["concerns"]).append(
                ("" if rough else "C3: ") + f"{r['date']}: JPL {r['jpl_km']:,.0f} km vs ESA {r['esa_km']:,.0f} km, {r['n_sigma']:.1f} sigma apart"
                + (" (both solutions very uncertain there)" if rough else ""))
    sentry = {}
    if rec["jpl_sentry"].get("ok"):
        sentry = json.loads(rec["jpl_sentry"]["text"])
    out["jpl_sentry"] = ("removed " + sentry["removed"]) if sentry.get("removed") else (
        "LISTED" if sentry.get("summary") else ("not listed" if "not found" in str(sentry.get("error", "")).lower()
                                                else "no answer"))
    if out["jpl_sentry"] == "LISTED":
        out["concerns"].append("C1: JPL Sentry lists the object")
    if rec["esa_risk_list"].get("ok"):
        lines = risk_list_lines(rec["esa_risk_list"]["text"], des)
        out["esa_risk_list"] = "LISTED" if lines else "not listed"
        out["esa_risk_lines"] = lines
        if lines:
            out["concerns"].append("C1: ESA risk list includes the object: " + lines[0].strip())
    else:
        out["esa_risk_list"] = "no answer"
    if rec["jpl_sbdb"].get("ok"):
        o = (json.loads(rec["jpl_sbdb"]["text"]) or {}).get("orbit") or {}
        out["jpl_orbit"] = {"orbit_id": o.get("orbit_id"), "n_obs_used": o.get("n_obs_used"),
                            "last_obs": o.get("last_obs"), "condition_code": o.get("condition_code")}
        jng = jpl_nongrav(json.loads(rec["jpl_sbdb"]["text"]))
        eng = esa_nongrav(rec["esa_orbit"]["text"]) if rec.get("esa_orbit", {}).get("ok") else {}
        out["nongrav"] = {"jpl": {k: list(v) for k, v in jng.items()}, "esa": {k: list(v) for k, v in eng.items()}}
        c6, n6 = nongrav_checks(jng, eng)
        out["concerns"] += c6
        out["notes"] += n6
    else:
        out["notes"].append("JPL orbit data unavailable: C6 (unexplained push) not checked this run")
    if rec["esa_observations"].get("ok"):
        out["esa_observations"] = observations_summary(rec["esa_observations"]["text"])
        jl, el = (out.get("jpl_orbit") or {}).get("last_obs"), out["esa_observations"]["last"]
        if jl and el and el > jl:
            out["notes"].append(f"ESA has observations after JPL's last ({el} vs {jl}): JPL may publish a new orbit")
    if out["jpl_sentry"] == "no answer" or out["esa_risk_list"] == "no answer":
        out["notes"].append("a risk list could not be reached; the no-impact conclusion rests on the other agency")
    out["verdict"] = CONCERN if out["concerns"] else CONSISTENT
    out["reason"] = ("; ".join(out["concerns"]) if out["concerns"] else
                     "JPL and ESA agree within their uncertainties, no pass reaches the atmosphere in either, "
                     "and neither risk list carries the object")
    return out


# ------------------------------------------------------------------ evidence ----
def write_evidence(records, analysis, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, r in records.items():
        entry = {k: r.get(k) for k in ("name", "url", "params", "retrieved_utc", "ok", "error", "sha256", "bytes")}
        if r.get("ok"):
            if r["bytes"] <= SMALL_BYTES:
                fn = f"{name}.{'json' if name.startswith('jpl') else 'txt'}"
                (folder / fn).write_bytes(r["text"].encode("utf-8"))
                entry["saved_as"] = fn
            else:
                entry["saved_as"] = None
                entry["note"] = "too large to keep each run; re-download and compare the sha256"
                if name == "esa_risk_list":
                    entry["header"] = r["text"].splitlines()[:1]
                    entry["matching_lines"] = analysis.get("esa_risk_lines", [])
                if name == "esa_observations":
                    entry["summary"] = analysis.get("esa_observations")
        manifest.append(entry)
    (folder / "manifest.json").write_text(json.dumps({"designation": analysis["designation"],
                                                      "checked_utc": analysis["checked_utc"],
                                                      "verdict": analysis["verdict"], "sources": manifest},
                                                     indent=2), encoding="utf-8")
    (folder / "analysis.json").write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
    lines = [f"{e['sha256']}  {e['saved_as']}" for e in manifest if e.get("saved_as")]
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def run(des="99942", net=None, evidence=None):
    records = capture(des, net)
    analysis = analyse(des, records)
    if evidence:
        write_evidence(records, analysis, evidence)
    return analysis, records


# ------------------------------------------------------------------ report ------
def format_report(a):
    lines = [f"  INDEPENDENT CROSS-CHECK  {a['designation']}  (NASA/JPL vs ESA NEOCC)  {a['checked_utc']} UTC"]
    if a["verdict"] == NO_DATA:
        return "\n".join(lines + [f"  NO DATA: {a['reason']}. No conclusion drawn."])
    jo = a.get("jpl_orbit") or {}
    eo = a.get("esa_observations") or {}
    lines.append(f"  JPL orbit {jo.get('orbit_id')}: {jo.get('n_obs_used')} observations used, last {jo.get('last_obs')}."
                 f"  ESA file: {eo.get('count')} observations ({eo.get('radar')} radar, {eo.get('from_space')} from space), "
                 f"last {eo.get('last')}.")
    lines.append(f"  Risk lists: JPL Sentry {a['jpl_sentry']}; ESA {a['esa_risk_list']}.")
    ng = a.get("nongrav") or {}
    if ng.get("jpl", {}).get("A2"):
        ja2, js2 = ng["jpl"]["A2"]
        ea = ng.get("esa", {}).get("A2")
        lines.append(f"  Yarkovsky push A2: JPL {ja2:.4e} +/- {js2:.1e} au/d^2"
                     + (f", ESA {ea[0]:.4e} +/- {ea[1]:.1e}" if ea and ea[0] is not None and ea[1] else "")
                     + f"  (C6 baseline {A2_BASELINE:.4e})")
    lines += ["", f"  {'pass (JPL TDB)':<22} {'JPL km':>12} {'ESA km':>12} {'diff km':>10} {'sigma':>6}  status"]
    for r in a["passes"]:
        if r["status"] in (AGREE, DISAGREE):
            lines.append(f"  {r['date']:<22} {r['jpl_km']:>12,.0f} {r['esa_km']:>12,.0f} {r['diff_km']:>+10,.1f} "
                         f"{r['n_sigma']:>6.1f}  {r['status']}")
        else:
            km = r.get("jpl_km") or r.get("esa_km")
            lines.append(f"  {r['date']:<22} {km:>12,.0f}  {r['status']} (the other agency lists no matching pass)")
    lines += ["", f"  VERDICT: {a['verdict']}. {a['reason']}."]
    for n in a["notes"]:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NASA/JPL vs ESA NEOCC cross-check with evidence trail")
    ap.add_argument("des", nargs="?", default="99942")
    ap.add_argument("--evidence", help="write raw replies, SHA256SUMS, manifest and analysis to this folder")
    ap.add_argument("--json", help="also write the analysis to this file")
    args = ap.parse_args(argv)
    a, _ = run(args.des, evidence=args.evidence)
    print(format_report(a))
    if args.json:
        Path(args.json).write_text(json.dumps(a, indent=2, default=str), encoding="utf-8")
    return {CONSISTENT: 0, NO_DATA: 2, CONCERN: 3}[a["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
